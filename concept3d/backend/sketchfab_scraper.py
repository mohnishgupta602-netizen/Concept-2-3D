import os
import re
import requests
from typing import Optional
import asyncio
import io
import zipfile
import tempfile
import shutil
try:
    import trimesh
except Exception:
    trimesh = None

# NOTE: This scraper attempts Playwright first (if installed and usable),
# then falls back to a best-effort requests-based extractor.


def _find_candidate_urls(page_text: str) -> list[str]:
    pattern = re.compile(r"https?://[^\'\"\s>]+?\.(?:glb|gltf)(?:\?[^\'\"\s>]*)?", re.IGNORECASE)
    urls = pattern.findall(page_text or "")
    seen = set()
    out = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


async def _async_playwright_download(model_url: str, download_dir: str) -> Optional[str]:
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return None

    os.makedirs(download_dir, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        found = {"url": None}

        async def _on_response(resp):
            try:
                u = resp.url
                if (".glb" in u or ".gltf" in u) and "media.sketchfab.com" in u:
                    found["url"] = u
            except Exception:
                pass

        page.on("response", _on_response)

        try:
            await page.goto(model_url, timeout=60000)
            await page.wait_for_timeout(5000)
        except Exception:
            await browser.close()
            return None

        model_url_found = found.get("url")
        if not model_url_found:
            await browser.close()
            return None

        filename = os.path.join(download_dir, os.path.basename(model_url_found.split("?")[0]))

        try:
            async with page.request.get(model_url_found) as resp:
                if resp.status == 200:
                    body = await resp.body()
                    with open(filename, "wb") as fh:
                        fh.write(body)
                    await browser.close()
                    return filename
        except Exception:
            pass

        await browser.close()
        return None


def _run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside a running event loop (e.g., uvicorn). Run the coroutine
        # in a new thread so we don't interfere with the server loop.
        import threading

        result_container = {"result": None, "error": None}

        def _target():
            try:
                result_container["result"] = asyncio.run(coro)
            except Exception as e:
                result_container["error"] = e

        t = threading.Thread(target=_target, daemon=True)
        t.start()
        t.join()
        if result_container.get("error"):
            raise result_container["error"]
        return result_container.get("result")

    return asyncio.run(coro)


def _playwright_scrape(model_url: str, download_dir: str) -> Optional[str]:
    try:
        return _run_async(_async_playwright_download(model_url, download_dir))
    except Exception as e:
        print(f"Playwright scraper error: {e}")
        return None


def scrape_sketchfab_model(model_url: str, download_dir: str) -> Optional[str]:
    """Attempt to download a Sketchfab model. Tries Playwright (if installed),
    then falls back to scanning the static HTML for .glb/.gltf links.
    """
    # Try Playwright first (more reliable for JS-heavy pages)
    try:
        result = _playwright_scrape(model_url, download_dir)
        if result:
            return result
    except Exception as e:
        print(f"Playwright attempt failed: {e}")

    # Fallback: best-effort static extraction + direct download
    os.makedirs(download_dir, exist_ok=True)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/114.0 Safari/537.36"
        ),
        "Referer": model_url,
    }

    try:
        resp = requests.get(model_url, headers=headers, timeout=20)
        resp.raise_for_status()
        page = resp.text

        candidates = _find_candidate_urls(page)
        if not candidates:
            # Search JSON-like blobs for embedded URLs
            script_urls = re.findall(r"\{[^}]*\}", page)
            for blob in script_urls:
                for u in _find_candidate_urls(blob):
                    if u not in candidates:
                        candidates.append(u)

        if not candidates:
            print("Sketchfab scraper: no .glb/.gltf URLs found in static page")
            return None

        for url in candidates:
            try:
                local_name = os.path.basename(url.split("?")[0])
                filename = os.path.join(download_dir, local_name)
                if os.path.exists(filename):
                    return filename
                print(f"Sketchfab scraper: trying static URL {url}")
                r = requests.get(url, headers=headers, timeout=60, stream=True)
                r.raise_for_status()
                content_type = r.headers.get("Content-Type", "")
                if (
                    "model/gltf+json" in content_type.lower()
                    or "model/gltf-binary" in content_type.lower()
                    or url.lower().endswith(".glb")
                ):
                    with open(filename, "wb") as fh:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk:
                                fh.write(chunk)
                    return filename
                else:
                    content_length = int(r.headers.get("Content-Length", "0") or "0")
                    if content_length > 1024:
                        with open(filename, "wb") as fh:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk:
                                    fh.write(chunk)
                        return filename
                    else:
                        print(f"Sketchfab scraper: candidate {url} has unexpected content-type {content_type}")
            except Exception as e:
                print(f"Sketchfab scraper: failed to download {url}: {e}")

        return None

    except Exception as e:
        print(f"Sketchfab scrape failed: {e}")
        return None


def _extract_urls_from_obj(obj) -> list[str]:
    urls = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                urls.extend(_extract_urls_from_obj(v))
            elif isinstance(v, str) and (v.lower().endswith('.glb') or v.lower().endswith('.gltf') or 'media.sketchfab.com' in v):
                urls.append(v)
    elif isinstance(obj, list):
        for item in obj:
            urls.extend(_extract_urls_from_obj(item))
    return urls


def _save_bytes_as_glb(binary: bytes, out_path: str) -> bool:
    bio = io.BytesIO(binary)
    # ZIP archive
    try:
        if zipfile.is_zipfile(bio):
            with tempfile.TemporaryDirectory() as td:
                bio.seek(0)
                with zipfile.ZipFile(bio) as zf:
                    zf.extractall(td)
                glb_files = []
                gltf_files = []
                for root, _, files in os.walk(td):
                    for f in files:
                        if f.lower().endswith('.glb'):
                            glb_files.append(os.path.join(root, f))
                        elif f.lower().endswith('.gltf'):
                            gltf_files.append(os.path.join(root, f))
                if glb_files:
                    shutil.copyfile(glb_files[0], out_path)
                    return True
                if gltf_files and trimesh is not None:
                    try:
                        scene = trimesh.load(gltf_files[0], force='scene')
                        exported = scene.export(file_type='glb')
                        with open(out_path, 'wb') as fh:
                            fh.write(exported)
                        return True
                    except Exception:
                        pass
            return False
    except Exception:
        pass

    # Check GLB header
    try:
        bio.seek(0)
        header = bio.read(16)
        if header[0:4] == b'glTF':
            with open(out_path, 'wb') as fh:
                fh.write(binary)
            return True
    except Exception:
        pass

    # Try loading as glTF via trimesh
    if trimesh is not None:
        try:
            with tempfile.TemporaryDirectory() as td:
                maybe = os.path.join(td, 'candidate.data')
                with open(maybe, 'wb') as fh:
                    fh.write(binary)
                scene = trimesh.load(maybe, force='scene')
                exported = scene.export(file_type='glb')
                with open(out_path, 'wb') as fh:
                    fh.write(exported)
                return True
        except Exception:
            pass

    # Last resort: write raw bytes
    try:
        with open(out_path, 'wb') as fh:
            fh.write(binary)
        return True
    except Exception:
        return False


def download_from_api(uid: str, download_dir: str, api_token: Optional[str] = None, api_quota: dict | None = None) -> Optional[str]:
    """Use Sketchfab API /v3/models/{uid}/download to find a downloadable asset and save it locally.

    Returns local filepath or None.
    """
    os.makedirs(download_dir, exist_ok=True)
    if api_quota is not None:
        # If quota exhausted, skip API usage
        if api_quota.get('remaining', 0) <= 0:
            print(f"Sketchfab API: quota exhausted; skipping API download for {uid}")
            return None
        # consume one API call for this download operation
        api_quota['remaining'] = api_quota.get('remaining', 0) - 1

    if not api_token:
        print(f"Sketchfab API: no API token provided; skipping API download for {uid}")
        return None
    headers = {'Authorization': f'Token {api_token}'}
    # Do not print the token; log presence only
    print(f"Sketchfab API: Authorization header present for download attempts for {uid}")

    # First check model metadata to ensure downloads are allowed
    try:
        meta_resp = requests.get(f'https://api.sketchfab.com/v3/models/{uid}', headers=headers, timeout=15)
        if meta_resp.status_code == 401:
            print(f"Sketchfab API: Unauthorized (401) when checking model {uid}. Check SKETCHFAB_API_TOKEN.")
            return None
        if meta_resp.status_code == 403:
            print(f"Sketchfab API: Forbidden (403) when checking model {uid}. Model may be private or downloads disabled.")
            return None
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        if not meta.get('isDownloadable', False):
            print(f"Sketchfab API: model {uid} is not downloadable (isDownloadable=false). Skipping.")
            return None
    except Exception as e:
        print(f"Sketchfab API metadata request failed for {uid}: {e}")
        return None

    try:
        resp = requests.get(f'https://api.sketchfab.com/v3/models/{uid}/download', headers=headers, timeout=25)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        # surface specific 401/403 messages earlier
        if isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code == 401:
            print(f"Sketchfab API: Unauthorized (401) when requesting download for {uid}. Check SKETCHFAB_API_TOKEN.")
        else:
            print(f"Sketchfab API download request failed for {uid}: {e}")
        return None

    candidates = _extract_urls_from_obj(data)
    if not candidates:
        print(f"Sketchfab API: no download URLs found in API response for {uid}")
        return None

    # try candidates
    for c in candidates:
        try:
            url = str(c)
            filename = os.path.join(download_dir, os.path.basename(url.split('?')[0]))
            download_headers = None if 'media.sketchfab.com' in url else headers
            r = requests.get(url, headers=download_headers, timeout=60)
            r.raise_for_status()
            if _save_bytes_as_glb(r.content, filename):
                return filename
        except Exception as e:
            print(f"Sketchfab API download attempt failed for {uid} url={c}: {e}")

    return None
