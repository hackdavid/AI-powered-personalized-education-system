"""
Automated screenshot capture for README documentation.
Captures all major dashboards and features using Playwright.
"""
import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright


BASE_URL = "https://ai-powered-personalized-education-system.onrender.com"
IMAGES_DIR = Path(__file__).parent.parent / "docs" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Demo credentials
CREDENTIALS = {
    'student': ('adrian.zimmerman.17@springfield.test', 'Test@1234'),
    'teacher': ('andrea.calderon.3@springfield.test', 'Test@1234'),
    'admin': ('admin@springfield.test', 'Test@1234'),
}


async def login(page, email, password):
    """Login to the platform."""
    await page.goto(f"{BASE_URL}/auth/login/")
    await page.fill('input[name="email"]', email)
    await page.fill('input[name="password"]', password)
    await page.click('button[type="submit"]')
    await page.wait_for_load_state('networkidle')
    await asyncio.sleep(2)  # Wait for animations


async def capture_screenshots():
    """Capture all dashboard screenshots."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()

        print("Starting screenshot capture...")

        # 1. Login page
        print("Capturing login page...")
        await page.goto(f"{BASE_URL}/auth/login/")
        await page.wait_for_load_state('networkidle')
        await page.screenshot(path=str(IMAGES_DIR / "screenshot-login.png"), full_page=False)

        # 2. School Admin Dashboard
        print("Capturing school admin dashboard...")
        await login(page, *CREDENTIALS['admin'])
        await page.goto(f"{BASE_URL}/school-admin/")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)
        await page.screenshot(path=str(IMAGES_DIR / "screenshot-admin-dashboard.png"), full_page=True)

        # 3. School Admin Analytics
        print("Capturing admin analytics...")
        await page.goto(f"{BASE_URL}/school-admin/analytics/")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)
        await page.screenshot(path=str(IMAGES_DIR / "screenshot-admin-analytics.png"), full_page=True)

        # 4. School Admin Enrollment
        print("Capturing admin enrollment...")
        await page.goto(f"{BASE_URL}/school-admin/enrollment/")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)
        await page.screenshot(path=str(IMAGES_DIR / "screenshot-admin-enrollment.png"), full_page=True)

        # 5. School Admin Classes List
        print("Capturing classes list...")
        await page.goto(f"{BASE_URL}/school-admin/classes/")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)
        await page.screenshot(path=str(IMAGES_DIR / "screenshot-admin-classes.png"), full_page=True)

        # 6. School Admin Subjects List
        print("Capturing subjects list...")
        await page.goto(f"{BASE_URL}/school-admin/subjects/")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)
        await page.screenshot(path=str(IMAGES_DIR / "screenshot-admin-subjects.png"), full_page=True)

        # Logout and login as teacher
        await page.goto(f"{BASE_URL}/auth/logout/")
        await page.wait_for_load_state('networkidle')

        # 7. Teacher Dashboard
        print("Capturing teacher dashboard...")
        await login(page, *CREDENTIALS['teacher'])
        await page.goto(f"{BASE_URL}/teacher/")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)
        await page.screenshot(path=str(IMAGES_DIR / "screenshot-teacher-dashboard.png"), full_page=True)

        # 8. Teacher Classes
        print("Capturing teacher classes...")
        await page.goto(f"{BASE_URL}/teacher/classes/")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)
        await page.screenshot(path=str(IMAGES_DIR / "screenshot-teacher-classes.png"), full_page=True)

        # 9. Teacher Gradebook
        print("Capturing teacher gradebook...")
        await page.goto(f"{BASE_URL}/teacher/gradebook/")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)
        await page.screenshot(path=str(IMAGES_DIR / "screenshot-teacher-gradebook.png"), full_page=True)

        # 10. Teacher Insights
        print("Capturing teacher insights...")
        await page.goto(f"{BASE_URL}/teacher/insights/")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(3)
        await page.screenshot(path=str(IMAGES_DIR / "screenshot-teacher-insights.png"), full_page=True)

        # Logout and login as student
        await page.goto(f"{BASE_URL}/auth/logout/")
        await page.wait_for_load_state('networkidle')

        # 11. Student Dashboard
        print("Capturing student dashboard...")
        await login(page, *CREDENTIALS['student'])
        await page.goto(f"{BASE_URL}/dashboard/")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)
        await page.screenshot(path=str(IMAGES_DIR / "screenshot-student-dashboard.png"), full_page=True)

        # 12. Student Chat/Tutor
        print("Capturing student chat...")
        await page.goto(f"{BASE_URL}/student/chat/")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)
        await page.screenshot(path=str(IMAGES_DIR / "screenshot-student-chat.png"), full_page=True)

        await browser.close()
        print(f"\nScreenshots saved to: {IMAGES_DIR}")
        print("Total screenshots captured: 12")


if __name__ == "__main__":
    asyncio.run(capture_screenshots())
