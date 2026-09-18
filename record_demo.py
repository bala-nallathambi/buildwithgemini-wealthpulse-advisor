import os
import shutil
import subprocess
import time
from playwright.sync_api import sync_playwright

def record():
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.expanduser("~/.cache/ms-playwright")
    
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

        print("Navigating to WealthPulse Advisor at http://localhost:8080/...")
        page.goto("http://localhost:8080/")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Prompt 1: Portfolio Rebalance (Core capability)
        print("Prompt 1: Portfolio Rebalance Drift Analysis...")
        chip = page.locator(".chip", has_text="Portfolio Rebalance")
        if chip.count() > 0:
            chip.first.click()
        else:
            page.fill("#input", "Calculate portfolio rebalance")
            page.click("#form button[type='submit']")

        print("Waiting for Portfolio Rebalance response...")
        page.wait_for_selector(".msg.agent .bubble:not(:has-text('…'))", timeout=60000)
        time.sleep(3)

        # Prompt 2: Manage Holdings Database Lookup Widget
        print("Prompt 2: Database lookup & Holdings Table Widget...")
        page.fill("#input", "Show my holdings")
        page.click("#send-btn")

        print("Waiting for Holdings Table Widget...")
        page.wait_for_selector(".holdings-table-card", timeout=60000)
        time.sleep(3)

        # Prompt 3: Rich Prompt - Botanical Advisory & Visual Interactive Breakdown
        print("Prompt 3: Botanical Advisory & Interactive Portfolio Visual...")
        page.fill("#input", "Consult herbal remedies for financial stress and generate visual breakdown")
        page.click("#send-btn")

        print("Waiting for Botanical Advisory & Visual response...")
        page.wait_for_selector(".msg.agent:nth-child(7) .bubble:not(:has-text('…'))", timeout=60000)
        time.sleep(4)

        context.close()
        browser.close()

    # Locate recorded video
    webm_files = [os.path.join(video_dir, f) for f in os.listdir(video_dir) if f.endswith(".webm")]
    if not webm_files:
        raise RuntimeError("No recorded video found!")

    src_webm = webm_files[0]
    out_mp4 = os.path.abspath("wealthpulse_demo.mp4")
    out_artifact = os.path.abspath("/config/.gemini/antigravity/brain/f8be2c4d-d55f-4d02-89bf-234b156fc7bc/wealthpulse_demo.mp4")

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
    
    shutil.copy(out_mp4, out_artifact)
    print(f"Demo video saved to {out_mp4} and copied to artifacts at {out_artifact}")

if __name__ == "__main__":
    record()
