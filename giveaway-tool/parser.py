import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class GiveawayInfo:
    is_giveaway: bool
    channels_to_join: list = field(default_factory=list)
    needs_repost: bool = False
    needs_comment: bool = False
    comment_text: Optional[str] = None
    end_date_hint: Optional[str] = None
    raw_text: str = ""


KEYWORDS = [
    "розыгрыш", "giveaway", "конкурс", "победитель",
    "выиграй", "разыгрываем", "приз", "подарок",
    "участвуй", "разыгрывается", "розыгрышь",
    "жми", "нажми", "нажать", "кнопку"
]

REPOST_KEYWORDS = [
    "перешли", "сделай репост", "репост", "поделись",
    "forward", "repost", "расшарь", "опубликуй у себя"
]

COMMENT_KEYWORDS = [
    "напиши в комментарии", "оставь комментарий", "комментируй",
    "напишите", "пишите в комментариях", "в комменты"
]

CHANNEL_PATTERNS = [
    r"@([\w]+)",
    r"t\.me/([\w]+)",
    r"telegram\.me/([\w]+)",
]


def detect_giveaway(text: str, custom_keywords: list = None) -> GiveawayInfo:
    if not text:
        return GiveawayInfo(is_giveaway=False)

    text_lower = text.lower()
    keywords = custom_keywords or KEYWORDS

    is_giveaway = any(kw.lower() in text_lower for kw in keywords)
    # Also check for emoji combos typical for giveaways
    emoji_indicators = ["🎁", "🎉", "🏆", "🎊", "🎯", "💰", "💵", "💸"]
    has_giveaway_emoji = sum(1 for e in emoji_indicators if e in text) >= 2

    if not is_giveaway and not has_giveaway_emoji:
        return GiveawayInfo(is_giveaway=False, raw_text=text)

    # Extract channels to join
    channels_to_join = []
    for pattern in CHANNEL_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            if m.lower() not in channels_to_join:
                channels_to_join.append(m.lower())

    # Check if repost needed
    needs_repost = any(kw.lower() in text_lower for kw in REPOST_KEYWORDS)

    # Check if comment needed
    needs_comment = any(kw.lower() in text_lower for kw in COMMENT_KEYWORDS)
    comment_text = None
    if needs_comment:
        # Try to extract what to comment (often "+", "участвую", number)
        comment_patterns = [
            r'напиши[а-я\s]*["\']([^"\']+)["\']',
            r'комментари[а-я\s]*["\']([^"\']+)["\']',
            r'напиши[те\s]+([+\w]+)',
        ]
        for cp in comment_patterns:
            m = re.search(cp, text_lower)
            if m:
                comment_text = m.group(1).strip()
                break
        if not comment_text:
            comment_text = "+"  # Default comment for giveaways

    # Try to detect end date
    date_pattern = r'(\d{1,2}[\./]\d{1,2}(?:[\./]\d{2,4})?)'
    date_match = re.search(date_pattern, text)
    end_date_hint = date_match.group(1) if date_match else None

    return GiveawayInfo(
        is_giveaway=True,
        channels_to_join=channels_to_join,
        needs_repost=needs_repost,
        needs_comment=needs_comment,
        comment_text=comment_text,
        end_date_hint=end_date_hint,
        raw_text=text
    )
