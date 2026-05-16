"""
Posts a Telegram Story with up to 50 user mentions (tags) per account per day.
Uses Pyrogram raw API because Story methods are not in the high-level API yet.
"""

import asyncio
import logging
import mimetypes
from pathlib import Path

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.raw import functions, types
from pyrogram.raw.types import (
    InputMediaUploadedPhoto,
    InputMediaUploadedDocument,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    InputPrivacyValueAllowAll,
    MediaAreaCoordinates,
)

logger = logging.getLogger(__name__)

MAX_TAGS_PER_STORY = 50  # Telegram hard limit
# Mention areas are placed in a non-overlapping grid on the story canvas
CANVAS_W, CANVAS_H = 9.0, 16.0


def _make_grid_coords(index: int, total: int) -> MediaAreaCoordinates:
    """Place mention badges in a vertical list on the left side of the story."""
    cols = 1
    rows = total
    row = index % rows
    x = 1.0  # % from left
    y = 5.0 + row * (CANVAS_H - 8.0) / max(rows, 1)
    return MediaAreaCoordinates(
        x=x, y=y, w=3.0, h=1.2, rotation=0.0
    )


async def _upload_media(client: Client, file_path: str):
    """Upload photo or video and return raw InputMedia."""
    path = Path(file_path)
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

    if mime.startswith("image/"):
        uploaded = await client.save_file(file_path)
        return InputMediaUploadedPhoto(file=uploaded, spoiler=False)
    else:
        uploaded = await client.save_file(file_path)
        return InputMediaUploadedDocument(
            file=uploaded,
            mime_type=mime,
            attributes=[
                DocumentAttributeFilename(file_name=path.name),
                DocumentAttributeVideo(
                    duration=0,
                    w=720,
                    h=1280,
                    round_message=False,
                    supports_streaming=True,
                    nosound=False,
                    preload_prefix_size=0,
                    video_start_ts=0.0,
                ),
            ],
            spoiler=False,
        )


async def post_story_with_tags(
    client: Client,
    media_path: str,
    user_ids: list[int],
    link_url: str | None = None,
    caption: str | None = None,
    period: int = 86400,  # story lifetime in seconds (max 86400 = 24h)
) -> int | None:
    """
    Upload media and post a Story tagging the given user_ids.
    Returns the story ID or None on failure.
    """
    if not user_ids:
        logger.warning("No users to tag.")
        return None

    tags = user_ids[:MAX_TAGS_PER_STORY]
    media = await _upload_media(client, media_path)

    # Build mention areas (InputMediaAreaProfile) for each user
    media_areas = []
    for i, uid in enumerate(tags):
        try:
            peer = await client.resolve_peer(uid)
        except Exception as exc:
            logger.debug("Cannot resolve user %d: %s", uid, exc)
            continue

        coords = _make_grid_coords(i, len(tags))
        # InputMediaAreaProfile places a tappable profile chip on the story
        media_areas.append(
            types.InputMediaAreaProfile(
                coordinates=coords,
                peer=peer,
            )
        )

    if not media_areas:
        logger.error("Could not resolve any user peers.")
        return None

    # Optional: add a URL sticker (link button on the story)
    if link_url:
        media_areas.append(
            types.InputMediaAreaUrl(
                coordinates=MediaAreaCoordinates(
                    x=3.0, y=13.5, w=3.0, h=1.2, rotation=0.0
                ),
                url=link_url,
            )
        )

    privacy = [InputPrivacyValueAllowAll()]

    try:
        result = await client.invoke(
            functions.stories.SendStory(
                peer=await client.resolve_peer("me"),
                media=media,
                media_areas=media_areas,
                caption=caption or "",
                entities=[],
                privacy_rules=privacy,
                period=period,
                pinned=False,
                noforwards=False,
                fwd_modified=False,
                fwd_from_id=None,
                fwd_from_story=0,
            )
        )
        story_id = result.updates[0].story.id if result.updates else None
        logger.info("Story posted (id=%s) with %d tags", story_id, len(media_areas))
        return story_id
    except FloodWait as e:
        logger.warning("FloodWait %ds when posting story", e.value)
        await asyncio.sleep(e.value)
        return None
    except Exception as exc:
        logger.error("Failed to post story: %s", exc)
        return None


async def run_story_tagger(
    session_path: str,
    api_id: int,
    api_hash: str,
    media_path: str,
    user_ids: list[int],
    link_url: str | None = None,
    caption: str | None = None,
    daily_limit: int = MAX_TAGS_PER_STORY,
    delay_between_resolves: float = 0.5,
) -> dict:
    """
    Tag users in stories across multiple story posts if needed.
    Respects the 50-tags-per-story Telegram limit.
    Returns stats dict.
    """
    stats = {"total": len(user_ids), "posted_stories": 0, "tagged": 0, "errors": 0}
    batch = user_ids[:daily_limit]

    async with Client(session_path, api_id=api_id, api_hash=api_hash) as client:
        for start in range(0, len(batch), MAX_TAGS_PER_STORY):
            chunk = batch[start : start + MAX_TAGS_PER_STORY]
            story_id = await post_story_with_tags(
                client,
                media_path=media_path,
                user_ids=chunk,
                link_url=link_url,
                caption=caption,
            )
            if story_id:
                stats["posted_stories"] += 1
                stats["tagged"] += len(chunk)
            else:
                stats["errors"] += 1

            if start + MAX_TAGS_PER_STORY < len(batch):
                await asyncio.sleep(5)

    return stats
