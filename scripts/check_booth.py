import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from urllib.parse import (
    parse_qsl,
    unquote,
    urlencode,
    urljoin,
    urlparse,
    urlunparse,
)

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
TARGETS_FILE = ROOT / "targets.json"
SEEN_FILE = ROOT / "seen_items.json"

MAX_ITEMS_PER_TARGET = 40
MAX_NOTIFY_PER_TARGET = 20
MAX_SEEN_IDS = 500
MAX_FREE_ITEM_CHECKS = 500
FREE_ITEM_CHECK_TTL = timedelta(hours=24)
GIF_FRAME_DURATION_MS = 1500
GIF_SIZE = (300, 300)
MAX_GIF_SIZE_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 5

CATEGORY_COLORS = {
    "3D": 0x8B5CF6,
    "イラスト": 0xEC4899,
    "アクセサリー": 0xF59E0B,
    "ファッション": 0xEF4444,
    "音楽": 0x3B82F6,
    "ゲーム": 0x10B981,
    "ソフトウェア": 0x64748B,
}
DEFAULT_EMBED_COLOR = 0xFC4D50

HEADERS = {
    "User-Agent": "booth-watcher/0.1 (+https://github.com/ekureaa/booth-watcher)"
}

REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def is_booth_host(hostname: str | None) -> bool:
    return hostname == "booth.pm" or bool(
        hostname and hostname.endswith(".booth.pm")
    )


def validate_https_url(url: str, allowed_hosts: set[str] | None = None) -> None:
    parsed = urlparse(url)
    hostname = parsed.hostname
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
    ):
        raise ValueError(f"Unsafe URL: {url}")
    if allowed_hosts is not None and hostname not in allowed_hosts:
        raise ValueError(f"Unexpected URL host: {hostname}")


def validate_booth_url(url: str) -> None:
    validate_https_url(url)
    if not is_booth_host(urlparse(url).hostname):
        raise ValueError(f"Unexpected BOOTH URL host: {urlparse(url).hostname}")


def validated_booth_url(base_url: str, value: str | None) -> str | None:
    if not value:
        return None
    url = urljoin(base_url, value)
    try:
        validate_booth_url(url)
    except ValueError:
        return None
    return url


def validated_image_url(base_url: str, value: str | None) -> str | None:
    if not value:
        return None
    url = urljoin(base_url, value)
    try:
        validate_https_url(url, {"booth.pximg.net"})
    except ValueError:
        return None
    return url


def get_with_validated_redirects(
    url: str,
    validator,
) -> requests.Response:
    current_url = url
    for _redirect_count in range(MAX_REDIRECTS + 1):
        validator(current_url)
        response = requests.get(
            current_url,
            headers=HEADERS,
            timeout=20,
            allow_redirects=False,
        )
        if response.status_code not in REDIRECT_STATUSES:
            return response

        location = response.headers.get("Location")
        response.close()
        if not location:
            raise ValueError(f"Redirect without Location: {current_url}")
        current_url = urljoin(current_url, location)

    raise ValueError(f"Too many redirects: {url}")


def load_targets() -> list[dict]:
    data = json.loads(TARGETS_FILE.read_text(encoding="utf-8"))
    targets = data.get("targets") if isinstance(data, dict) else None
    if not isinstance(targets, list):
        raise ValueError("targets.json: targets must be an array")

    for index, target in enumerate(targets, start=1):
        if not isinstance(target, dict):
            raise ValueError(f"targets.json: target {index} must be an object")

        webhook_name = target.get("webhook_name")
        url = target.get("url")
        free_only = target.get("free_only")
        if not isinstance(webhook_name, str) or not webhook_name:
            raise ValueError(
                f"targets.json: target {index} requires webhook_name"
            )
        if not isinstance(url, str):
            raise ValueError(
                f"targets.json: target {index} requires a BOOTH url"
            )
        try:
            validate_https_url(url, {"booth.pm"})
        except ValueError as error:
            raise ValueError(
                f"targets.json: target {index} requires an HTTPS booth.pm url"
            ) from error
        if not isinstance(free_only, bool):
            raise ValueError(
                f"targets.json: target {index} requires boolean free_only"
            )

    return targets


def load_webhook_urls() -> dict[str, str]:
    webhook_urls = {}
    raw_webhook_urls = os.environ.get("DISCORD_WEBHOOK_URLS")

    if raw_webhook_urls:
        parsed = json.loads(raw_webhook_urls)
        if not isinstance(parsed, dict) or not all(
            isinstance(name, str) and isinstance(url, str)
            for name, url in parsed.items()
        ):
            raise ValueError("DISCORD_WEBHOOK_URLS must be a JSON object")
        webhook_urls.update(parsed)

    # 単一Webhookを使っていた旧設定との後方互換性
    default_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if default_url:
        webhook_urls.setdefault("default", default_url)

    return webhook_urls


def load_seen_ids() -> tuple[
    dict[str, set[str]], set[str] | None, dict[str, dict]
]:
    if not SEEN_FILE.exists():
        return {}, None, {}

    data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    if "channels" in data:
        channels = data["channels"]
        if not isinstance(channels, dict):
            raise ValueError("seen_items.json: channels must be an object")
        seen_ids_by_channel = {
            name: set(item_ids)
            for name, item_ids in channels.items()
        }
        free_item_checks = data.get("free_item_checks", {})
        if not isinstance(free_item_checks, dict):
            raise ValueError("seen_items.json: free_item_checks must be an object")
        return seen_ids_by_channel, None, free_item_checks

    # 旧形式は起動時に設定済みの全通知先へ引き継ぐ。
    return {}, set(data.get("seen_ids", [])), {}


def save_seen_ids(
    seen_ids_by_channel: dict[str, set[str]],
    free_item_checks: dict[str, dict],
) -> None:
    latest_free_item_checks = dict(
        sorted(
            free_item_checks.items(),
            key=lambda entry: entry[1].get("checked_at", ""),
        )[-MAX_FREE_ITEM_CHECKS:]
    )
    data = {
        "channels": {
            channel: sorted(item_ids, key=int)[-MAX_SEEN_IDS:]
            for channel, item_ids in sorted(seen_ids_by_channel.items())
        },
        "free_item_checks": latest_free_item_checks,
    }
    SEEN_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def extract_image_url(link, base_url: str) -> str | None:
    direct_url = link.get("data-original")
    if direct_url:
        return validated_image_url(base_url, direct_url)

    image = link.find("img")
    if image is None:
        return None

    for attribute in ("data-src", "data-original", "src"):
        value = image.get(attribute)
        if value and not value.startswith("data:"):
            if image_url := validated_image_url(base_url, value):
                return image_url

    srcset = image.get("data-srcset") or image.get("srcset")
    if srcset:
        candidates = [part.strip().split()[0] for part in srcset.split(",")]
        for candidate in reversed(candidates):
            if image_url := validated_image_url(base_url, candidate):
                return image_url

    return None


def extract_browse_category(base_url: str) -> tuple[str, str] | None:
    parsed = urlparse(base_url)
    path_parts = parsed.path.strip("/").split("/")

    try:
        browse_index = path_parts.index("browse")
        encoded_category = path_parts[browse_index + 1]
    except (ValueError, IndexError):
        return None

    category_name = unquote(encoded_category)
    category_url = f"{parsed.scheme}://{parsed.netloc}/" + "/".join(
        path_parts[:browse_index + 2]
    )
    return category_name, category_url


def extract_items(html: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    items_by_id = {}
    browse_category = extract_browse_category(base_url)

    # BOOTHの一覧カードから、同じ商品に属する情報をまとめて取得する。
    for card in soup.select(".item-card[data-product-id]"):
        item_id = card.get("data-product-id")
        item_link = card.select_one(".item-card__title a[href*='/items/']")
        if not item_id or item_link is None:
            continue
        item_url = validated_booth_url(base_url, item_link.get("href"))
        item_url_match = (
            re.fullmatch(r"/(?:[a-z]{2}/)?items/(\d+)", urlparse(item_url).path)
            if item_url else None
        )
        if not item_url_match or item_url_match.group(1) != item_id:
            continue

        title = " ".join(item_link.get_text(" ", strip=True).split())
        category = card.select_one(".item-card__category-anchor")
        if category:
            category_name = category.get_text(" ", strip=True)
            category_url = validated_booth_url(base_url, category.get("href"))
        elif browse_category:
            category_name, category_url = browse_category
        else:
            category_name, category_url = "不明", None
        shop = card.select_one(".item-card__shop-name")
        shop_link = card.select_one(".item-card__shop-name-anchor")
        shop_icon = shop_link.select_one("img") if shop_link else None
        price = card.select_one(".price")
        event_names = [
            event.get_text(" ", strip=True)
            for event in card.select(".eventname-flag__name")
        ]
        badges = [
            badge.get("alt")
            for badge in card.select(".l-item-card-badge img[alt]")
            if badge.get("alt")
        ]
        thumbnail_links = card.select(".item-card__thumbnail-image")
        shop_url = validated_booth_url(
            base_url, shop_link.get("href") if shop_link else None
        )
        shop_icon_url = validated_image_url(
            base_url, shop_icon.get("src") if shop_icon else None
        )
        item = {
            "id": item_id,
            "title": title or card.get("data-product-name") or f"BOOTH item {item_id}",
            "url": item_url,
            "shop_name": shop.get_text(" ", strip=True) if shop else "不明",
            "shop_url": shop_url,
            "shop_icon_url": shop_icon_url,
            "category_name": category_name,
            "category_url": category_url,
            "price": price.get_text(" ", strip=True) if price else "不明",
            "event_names": list(dict.fromkeys(event_names)),
            "badges": list(dict.fromkeys(badges)),
        }
        image_urls = list(dict.fromkeys(
            image_url
            for link in thumbnail_links
            if (image_url := extract_image_url(link, base_url))
        ))
        if image_urls:
            item["image_url"] = image_urls[0]
            item["image_urls"] = image_urls

        items_by_id[item_id] = item
        items.append(item)

    # カード形式が変わった場合も、商品リンクだけは従来どおり検出する。
    for a in soup.find_all("a", href=True):
        href = a["href"]
        url = validated_booth_url(base_url, href)
        if url is None:
            continue

        match = re.search(r"/items/(\d+)", urlparse(url).path)
        if not match:
            continue

        item_id = match.group(1)
        title = " ".join(a.get_text(" ", strip=True).split())
        image_url = extract_image_url(a, base_url)

        if item_id not in items_by_id:
            item = {
                "id": item_id,
                "title": title or f"BOOTH item {item_id}",
                "url": url,
                "shop_name": "不明",
                "shop_url": None,
                "shop_icon_url": None,
                "category_name": browse_category[0] if browse_category else "不明",
                "category_url": browse_category[1] if browse_category else None,
                "price": "不明",
                "event_names": [],
                "badges": [],
            }
            if image_url:
                item["image_url"] = image_url
                item["image_urls"] = [image_url]
            items_by_id[item_id] = item
            items.append(item)
            continue

        item = items_by_id[item_id]
        if title and item["title"] == f"BOOTH item {item_id}":
            item["title"] = title
        if image_url and "image_url" not in item:
            item["image_url"] = image_url
            item["image_urls"] = [image_url]

    return items[:MAX_ITEMS_PER_TARGET]


def fetch_items(target_url: str) -> list[dict]:
    response = get_with_validated_redirects(target_url, validate_booth_url)
    response.raise_for_status()
    return extract_items(response.text, target_url)


def remove_price_filters(target_url: str) -> str:
    parsed = urlparse(target_url)
    query = [
        (name, value)
        for name, value in parse_qsl(parsed.query, keep_blank_values=True)
        if name not in {"min_price", "max_price"}
    ]
    return urlunparse(parsed._replace(query=urlencode(query)))


def extract_low_price(html: str) -> float | None:
    soup = BeautifulSoup(html, "html.parser")

    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
        except (TypeError, json.JSONDecodeError):
            continue

        products = data if isinstance(data, list) else [data]
        for product in products:
            if not isinstance(product, dict) or product.get("@type") != "Product":
                continue

            offers = product.get("offers")
            if not isinstance(offers, dict):
                continue
            price = offers.get("lowPrice", offers.get("price"))
            try:
                return float(str(price).replace(",", ""))
            except (TypeError, ValueError):
                continue

    return None


def fetch_is_free_item(item_url: str) -> bool:
    response = get_with_validated_redirects(item_url, validate_booth_url)
    response.raise_for_status()
    low_price = extract_low_price(response.text)
    if low_price is None:
        raise ValueError("Could not find the item price")
    return low_price == 0


def get_cached_free_status(
    item_id: str,
    free_item_checks: dict[str, dict],
    now: datetime,
) -> bool | None:
    cached = free_item_checks.get(item_id)
    if not isinstance(cached, dict) or not isinstance(cached.get("is_free"), bool):
        return None

    try:
        checked_at = datetime.fromisoformat(cached["checked_at"])
    except (KeyError, TypeError, ValueError):
        return None
    if checked_at.tzinfo is None or now - checked_at >= FREE_ITEM_CHECK_TTL:
        return None
    return cached["is_free"]


def filter_free_items(
    items: list[dict], free_item_checks: dict[str, dict]
) -> list[dict]:
    free_items = []

    for item in items:
        now = datetime.now(timezone.utc)
        is_free = get_cached_free_status(item["id"], free_item_checks, now)
        if is_free is None:
            try:
                is_free = fetch_is_free_item(item["url"])
            except Exception as e:
                print(f"Failed to check item price {item['url']}: {e}")
                continue

            free_item_checks[item["id"]] = {
                "is_free": is_free,
                "checked_at": now.isoformat(),
            }
            time.sleep(1)

        if is_free:
            item["price"] = "¥ 0～"
            free_items.append(item)

    return free_items


def create_animated_gif(image_urls: list[str]) -> bytes | None:
    frames = []

    for image_url in image_urls:
        try:
            response = get_with_validated_redirects(
                image_url,
                lambda url: validate_https_url(url, {"booth.pximg.net"}),
            )
            response.raise_for_status()
            with Image.open(BytesIO(response.content)) as image:
                frame = ImageOps.fit(
                    image.convert("RGB"),
                    GIF_SIZE,
                    method=Image.Resampling.LANCZOS,
                )
                frames.append(frame)
        except Exception as e:
            print(f"Failed to fetch GIF frame {image_url}: {e}")

    if len(frames) < 2:
        return None

    output = BytesIO()
    frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=GIF_FRAME_DURATION_MS,
        loop=0,
        optimize=True,
        disposal=2,
    )
    gif_data = output.getvalue()
    if len(gif_data) > MAX_GIF_SIZE_BYTES:
        print("Animated GIF is too large; use the first image instead.")
        return None
    return gif_data


def get_category_color(category_name: str) -> int:
    for prefix, color in CATEGORY_COLORS.items():
        if category_name.startswith(prefix):
            return color
    return DEFAULT_EMBED_COLOR


def send_discord_message(item: dict, webhook_url: str) -> None:
    parsed_webhook_url = urlparse(webhook_url)
    validate_https_url(webhook_url, {"discord.com", "discordapp.com"})
    if not re.fullmatch(
        r"/api/webhooks/\d+/[A-Za-z0-9._-]+", parsed_webhook_url.path
    ):
        raise ValueError("Invalid Discord Webhook URL")
    shop_name = item.get("shop_name", "不明")
    category_name = item.get("category_name", "不明")
    category_url = item.get("category_url")
    category_value = (
        f"[{category_name}]({category_url})" if category_url else category_name
    )
    embed = {
        "title": item["title"][:256],
        "url": item["url"],
        "color": get_category_color(category_name),
        "author": {"name": shop_name[:256]},
        "fields": [
            {
                "name": "価格",
                "value": item.get("price", "不明"),
                "inline": True,
            },
            {"name": "カテゴリ", "value": category_value, "inline": True},
        ],
        "footer": {"text": f"BOOTH Item #{item['id']}"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if item.get("shop_url"):
        embed["author"]["url"] = item["shop_url"]
    if item.get("shop_icon_url"):
        embed["author"]["icon_url"] = item["shop_icon_url"]
    if item.get("event_names"):
        embed["fields"].append({
            "name": "イベント",
            "value": " / ".join(item["event_names"]),
            "inline": False,
        })
    if item.get("badges"):
        embed["fields"].append({
            "name": "対応・バッジ",
            "value": " / ".join(item["badges"]),
            "inline": False,
        })
    image_urls = item.get("image_urls", [])
    animated_gif = create_animated_gif(image_urls) if len(image_urls) > 1 else None
    if animated_gif:
        embed["image"] = {"url": "attachment://booth-item.gif"}
    elif item.get("image_url"):
        embed["image"] = {"url": item["image_url"]}

    payload = {
        "embeds": [embed]
    }

    if animated_gif:
        response = requests.post(
            webhook_url,
            data={"payload_json": json.dumps(payload, ensure_ascii=False)},
            files={
                "files[0]": ("booth-item.gif", animated_gif, "image/gif")
            },
            timeout=20,
            allow_redirects=False,
        )
    else:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=20,
            allow_redirects=False,
        )
    if response.status_code in REDIRECT_STATUSES:
        raise ValueError("Discord Webhook unexpectedly redirected")
    response.raise_for_status()


def main() -> None:
    targets = load_targets()
    webhook_urls = load_webhook_urls()
    seen_ids_by_channel, legacy_seen_ids, free_item_checks = load_seen_ids()

    missing_webhooks = sorted(
        {target["webhook_name"] for target in targets} - webhook_urls.keys()
    )
    if missing_webhooks:
        raise ValueError(
            "Webhook URL is not configured for: " + ", ".join(missing_webhooks)
        )

    configured_channels = {target["webhook_name"] for target in targets}
    if legacy_seen_ids is not None:
        seen_ids_by_channel.update(
            {channel: set(legacy_seen_ids) for channel in configured_channels}
        )

    initialized_channels = set(seen_ids_by_channel)
    current_items_by_channel: dict[str, dict[str, dict]] = {}
    current_items_by_target: list[tuple[str, list[dict]]] = []
    successfully_fetched_channels = set()

    for target in targets:
        target_url = target["url"]
        webhook_name = target["webhook_name"]
        print(f"Checking ({webhook_name}): {target_url}")
        try:
            fetch_url = (
                remove_price_filters(target_url)
                if target["free_only"] else target_url
            )
            items = fetch_items(fetch_url)
            if target["free_only"]:
                items = filter_free_items(items, free_item_checks)
            print(f"Found items: {len(items)}")
            for item in items[:3]:
                print(f"  - {item['id']} {item['title']} {item['url']}")
        except Exception as e:
            print(f"Failed to fetch {target_url}: {e}")
            continue

        successfully_fetched_channels.add(webhook_name)
        current_items_by_target.append((webhook_name, items))
        channel_items = current_items_by_channel.setdefault(webhook_name, {})
        for item in items:
            channel_items.setdefault(item["id"], item)

        # BOOTHへの連続アクセスを避ける
        time.sleep(3)

    for channel in successfully_fetched_channels - initialized_channels:
        current_ids = set(current_items_by_channel.get(channel, {}))
        seen_ids_by_channel[channel] = current_ids
        print(f"First run for {channel}: save current items only, no notification.")

    new_items_count = sum(
        item_id not in seen_ids_by_channel[channel]
        for channel, items in current_items_by_channel.items()
        if channel in initialized_channels
        for item_id in items
    )
    notify_groups: list[list[tuple[dict, str]]] = []
    selected_ids_by_channel: dict[str, set[str]] = {
        channel: set() for channel in initialized_channels
    }

    for channel, items in current_items_by_target:
        if channel not in initialized_channels:
            continue

        selected_ids = selected_ids_by_channel[channel]
        target_items = [
            (item, channel)
            for item in items
            if item["id"] not in seen_ids_by_channel[channel]
            and item["id"] not in selected_ids
        ][:MAX_NOTIFY_PER_TARGET]
        selected_ids.update(item["id"] for item, _channel in target_items)
        notify_groups.append(target_items)

    notified_count = 0

    for notify_items in notify_groups:
        for item, webhook_name in reversed(notify_items):
            print(f"Notify ({webhook_name}): {item['title']} {item['url']}")
            try:
                send_discord_message(item, webhook_urls[webhook_name])
            except Exception as e:
                print(f"Failed to notify Discord: {e}")
            else:
                seen_ids_by_channel[webhook_name].add(item["id"])
                notified_count += 1

            time.sleep(1)

    save_seen_ids(seen_ids_by_channel, free_item_checks)

    print(f"New items: {new_items_count}, notified: {notified_count}")


if __name__ == "__main__":
    main()
