"""Delivery orchestration — ties the digest, the broadcaster and scheduling.

The scheduler calls :func:`run_due_deliveries` once a minute. Each chat has its
own multi-slot schedule (``Group.digest_times``); for every slot that has come
due and not yet been delivered today, the chat receives a freshly built digest.
Urgent news (score ``> 8``) is pushed as a separate alert outside the schedule.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from aiogram import Bot

from app.collectors.base import make_http_client
from app.config import ALL_DIGEST_WEEKDAYS, get_settings, parse_hhmm
from app.db import repositories as repo
from app.db.base import session_scope
from app.db.models import Group, NewsItem
from app.domain.enums import DeliveryStatus, NewsStatus
from app.logging import get_logger
from app.services.broadcaster import Broadcaster
from app.services.digest import (
    build_digest_content,
    ensure_item_image,
    render_breaking_news,
)
from app.utils.timeutil import now_in

log = get_logger(__name__)


@dataclass(slots=True)
class DeliveryReport:
    due_chats: int = 0
    sent: int = 0
    skipped: int = 0
    failed: int = 0
    blocked: int = 0


@dataclass(slots=True)
class BreakingDeliveryReport:
    candidates: int = 0
    sent_items: int = 0
    sent_chats: int = 0
    failed_chats: int = 0
    blocked_chats: int = 0
    downgraded_to_digest: int = 0


def _group_days(group: Group) -> set[int]:
    """Configured ISO weekdays for scheduled digests; defaults to every day."""
    return set(group.digest_days or ALL_DIGEST_WEEKDAYS)


def _due_slots(group: Group) -> tuple[date, list[str]]:
    """Return ``(local_date, slots_due_now)`` for *group*.

    A slot is due when the chat's local clock has reached it and it has not yet
    been delivered today. Using ``>=`` (not an exact match) means a missed
    scheduler tick is simply caught on the next one.
    """
    local = now_in(group.timezone)
    today = local.date()
    if local.isoweekday() not in _group_days(group):
        return today, []
    done = group.sent_slots_today if group.last_digest_on == today else []
    due: list[str] = []
    for slot in group.digest_times:
        if slot in done:
            continue
        try:
            target = parse_hhmm(slot)
        except ValueError:  # pragma: no cover -- guarded on input
            continue
        if local.time() >= target:
            due.append(slot)
    return today, due


async def run_due_deliveries(bot: Bot) -> DeliveryReport:
    """Deliver a digest to every chat that has a slot due right now."""
    report = DeliveryReport()

    async with session_scope() as session:
        groups = await repo.list_active_groups(session)
        # (group, local_date, due_slots) — one entry per chat with work to do.
        due: list[tuple[Group, date, list[str]]] = []
        for group in groups:
            if group.digest_paused:
                continue
            today, slots = _due_slots(group)
            if slots:
                due.append((group, today, slots))

    report.due_chats = len(due)
    if not due:
        return report

    log.info("delivery.due", chats=len(due))

    # Build the digest once for this tick — all due chats get the same edition.
    app_date = now_in(get_settings().timezone).date()
    content = await build_digest_content(app_date)

    if content.is_empty:
        async with session_scope() as session:
            for group, today, slots in due:
                for slot in slots:
                    await repo.mark_slot_sent(session, group.id, today, slot)
                await repo.log_delivery(
                    session,
                    group_id=group.id,
                    digest_date=today,
                    slot=slots[-1],
                    item_count=0,
                    status=DeliveryStatus.SKIPPED,
                )
        report.skipped = len(due)
        log.info("delivery.skipped_empty", chats=len(due))
        return report

    broadcaster = Broadcaster(bot)
    result = await broadcaster.deliver_digest(
        content.header, content.cards, [g.id for g, _, _ in due]
    )
    sent = set(result.sent)
    blocked = set(result.blocked)

    async with session_scope() as session:
        for group, today, slots in due:
            if group.id in sent:
                for slot in slots:
                    await repo.mark_slot_sent(session, group.id, today, slot)
                await repo.log_delivery(
                    session,
                    group_id=group.id,
                    digest_date=today,
                    slot=slots[-1],
                    item_count=len(content.item_ids),
                    status=DeliveryStatus.SENT,
                )
            elif group.id in blocked:
                await repo.deactivate_group(session, group.id)
                await repo.log_delivery(
                    session,
                    group_id=group.id,
                    digest_date=today,
                    slot=slots[-1],
                    item_count=0,
                    status=DeliveryStatus.FAILED,
                    error="bot blocked or removed",
                )
            else:
                await repo.log_delivery(
                    session,
                    group_id=group.id,
                    digest_date=today,
                    slot=slots[-1],
                    item_count=0,
                    status=DeliveryStatus.FAILED,
                    error=result.failed.get(group.id, "unknown error"),
                )

    report.sent = len(result.sent)
    report.blocked = len(result.blocked)
    report.failed = len(result.failed)
    return report


async def _downgrade_breaking_to_digest(item_ids: list[uuid.UUID]) -> int:
    """Return urgent items back to scheduled delivery when no instant push is possible."""
    if not item_ids:
        return 0
    async with session_scope() as session:
        downgraded = 0
        for item_id in item_ids:
            item = await repo.set_status(session, item_id, NewsStatus.APPROVED)
            if item is not None:
                downgraded += 1
        return downgraded


async def _fetch_breaking_candidates(
    item_ids: list[uuid.UUID] | None = None,
) -> tuple[list[NewsItem], list[Group]]:
    """Load urgent items (with preview images) and chats eligible for alerts."""
    async with session_scope() as session:
        items = await repo.list_breaking_news(session, item_ids=item_ids)
        active = await repo.list_active_groups(session)
        groups = [group for group in active if not group.digest_paused]
        # Fetch preview images for the urgent items, persisted on commit.
        if items:
            async with make_http_client() as client:
                for item in items:
                    await ensure_item_image(client, item)
    return items, groups


async def run_breaking_deliveries(
    bot: Bot, item_ids: list[uuid.UUID] | None = None
) -> BreakingDeliveryReport:
    """Push urgent items (score ``> 8``) outside the normal schedule.

    Day/time restrictions are bypassed, but a chat-level pause is still
    respected as an explicit "do not disturb" switch.
    """
    items, groups = await _fetch_breaking_candidates(item_ids)
    report = BreakingDeliveryReport(candidates=len(items))
    if not items:
        return report
    if not groups:
        report.downgraded_to_digest = await _downgrade_breaking_to_digest(
            [item.id for item in items]
        )
        return report

    broadcaster = Broadcaster(bot)
    chat_ids = [group.id for group in groups]
    local_dates = {group.id: now_in(group.timezone).date() for group in groups}

    for item in items:
        result = await broadcaster.broadcast(
            render_breaking_news(item), chat_ids, image_url=item.image_url or None
        )
        sent = set(result.sent)
        blocked = set(result.blocked)

        async with session_scope() as session:
            for group in groups:
                if group.id in sent:
                    await repo.log_delivery(
                        session,
                        group_id=group.id,
                        digest_date=local_dates[group.id],
                        slot=None,
                        item_count=1,
                        status=DeliveryStatus.SENT,
                    )
                elif group.id in blocked:
                    await repo.deactivate_group(session, group.id)
                    await repo.log_delivery(
                        session,
                        group_id=group.id,
                        digest_date=local_dates[group.id],
                        slot=None,
                        item_count=0,
                        status=DeliveryStatus.FAILED,
                        error="bot blocked or removed",
                    )
                else:
                    await repo.log_delivery(
                        session,
                        group_id=group.id,
                        digest_date=local_dates[group.id],
                        slot=None,
                        item_count=0,
                        status=DeliveryStatus.FAILED,
                        error=result.failed.get(group.id, "unknown error"),
                    )

            if sent:
                await repo.mark_posted(session, [item.id])
                report.sent_items += 1
            elif not result.failed:
                item_row = await repo.set_status(session, item.id, NewsStatus.APPROVED)
                if item_row is not None:
                    report.downgraded_to_digest += 1

        report.sent_chats += len(result.sent)
        report.failed_chats += len(result.failed)
        report.blocked_chats += len(result.blocked)

    log.info(
        "delivery.breaking_done",
        candidates=report.candidates,
        sent_items=report.sent_items,
        sent_chats=report.sent_chats,
        failed_chats=report.failed_chats,
        blocked_chats=report.blocked_chats,
        downgraded=report.downgraded_to_digest,
    )
    return report


async def deliver_now(bot: Bot, chat_id: int) -> tuple[bool, int]:
    """Force-send a digest to a single chat now (``/digest_now``).

    Returns ``(ok, item_count)``. This is an extra, manual delivery — it does
    not consume a scheduled slot, so the chat's regular schedule is unaffected.
    """
    async with session_scope() as session:
        group = await repo.get_group(session, chat_id)
        registered = group is not None
        tz = group.timezone if group else get_settings().timezone
    local_date = now_in(tz).date()

    content = await build_digest_content(local_date)
    broadcaster = Broadcaster(bot)
    result = await broadcaster.deliver_digest(content.header, content.cards, [chat_id])
    if chat_id not in result.sent:
        log.warning(
            "delivery.manual_failed",
            chat_id=chat_id,
            error=result.failed.get(chat_id, "blocked"),
        )
        return False, 0

    if registered:
        async with session_scope() as session:
            await repo.log_delivery(
                session,
                group_id=chat_id,
                digest_date=local_date,
                slot=None,
                item_count=len(content.item_ids),
                status=DeliveryStatus.SENT,
            )
    return True, len(content.item_ids)
