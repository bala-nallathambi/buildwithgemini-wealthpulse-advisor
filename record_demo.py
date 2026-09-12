import os
import shutil
import subprocess
import time
from playwright.sync_api import sync_playwright

def record():
    video_dir = os.path.abspath("video_temp")
    if os.path.exists(video_dir):
        shutil.rmtree(video_dir)
    os.makedirs(video_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            record_video_dir=video_dir,
            record_video_size={"width": 1280, "height": 720}
        )
        page = context.new_page()

        print("Navigating to http://localhost:8080/...")
        page.goto("http://localhost:8080/")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Prompt 1: Rebalance Portfolio via Chip click
        print("Prompt 1: Portfolio Rebalance...")
        chip = page.locator(".chip", has_text="Portfolio Rebalance")
        if chip.count() > 0:
            chip.first.click()
        else:
            page.fill("#input", "Calculate portfolio rebalance")
            page.click("#form button[type='submit']")

        # Wait for agent response
        print("Waiting for response 1...")
        page.wait_for_selector(".msg.agent .bubble:not(:has-text('…'))", timeout=60000)
        time.sleep(4)

        # Prompt 2: Rich prompt showing tool call & image generation
        print("Prompt 2: Generate visual portfolio chart...")
        page.fill("#input", "Generate a visual portfolio breakdown chart")
        page.click("#form button[type='submit']")

        print("Waiting for response 2 (tool call & image generation)...")
        page.wait_for_selector(".msg.agent:nth-child(3) .bubble:not(:has-text('…'))", timeout=60000)

        # Wait extra time for image element to load
        page.wait_for_timeout(5000)
        time.sleep(3)

        context.close()
        browser.close()

    # Find recorded webm file
    webm_files = [os.path.join(video_dir, f) for f in os.listdir(video_dir) if f.endswith(".webm")]
    if not webm_files:
        raise RuntimeError("No recorded video found!")
    
    src_webm = webm_files[0]
    out_mp4 = os.path.abspath("wealthpulse_demo.mp4")
    print(f"Converting {src_webm} to {out_mp4}...")
    
    cmd = [
        "ffmpeg", "-y",
        "-i", src_webm,
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        out_mp4
    ]
    subprocess.run(cmd, check=True)
    print(f"Demo video saved to {out_mp4}")

if __name__ == "__main__":
    record()
