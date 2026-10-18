"""玻璃与动效改版的布局、焦点及快速操作回归；不修改业务源文件。"""
import json
import os
import sys
from pathlib import Path

os.environ['TEMP'] = os.environ['TMP'] = 'D:/dev-env/tmp'
from playwright.sync_api import sync_playwright, expect
from 验收辅助 import choose_option, navigate

OUT = Path(__file__).parent / '验收截图'
URL = 'http://127.0.0.1:4178/'
results, errors = [], []
focus_only = '--focus-only' in sys.argv


def check(value, message):
    if not value:
        raise AssertionError(message)


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    page = context.new_page()
    page.set_default_timeout(6000)
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' else None)

    def case(name, fn):
        if focus_only and name not in ['弹窗关闭与保存后的焦点','整改与修订保存后的焦点','助手显式焦点不被弹窗回焦覆盖','补充流程浏览器错误']:
            return
        try:
            detail = fn()
            results.append({'name': name, 'passed': True, 'detail': detail})
            print('PASS', name, detail, flush=True)
        except Exception as error:
            results.append({'name': name, 'passed': False, 'detail': str(error)})
            print('FAIL', name, error, flush=True)
            page.screenshot(path=str(OUT / f'玻璃回归失败-{len(results)}.png'), full_page=True, animations='disabled')

    def open_fresh(suffix=''):
        page.goto(URL + suffix)
        expect(page.locator('main')).to_be_visible()

    def dialog_focus():
        page.set_viewport_size({'width': 1440, 'height': 1000})
        open_fresh()
        for method in ['escape', 'cancel', 'save']:
            trigger = page.locator('.sidebar [data-action="settings"]')
            trigger.click()
            expect(page.get_by_role('dialog')).to_be_visible()
            if method == 'escape':
                page.keyboard.press('Escape')
            elif method == 'cancel':
                page.get_by_role('dialog').get_by_role('button', name='取消', exact=True).click()
            else:
                page.get_by_role('dialog').get_by_role('button', name='保存设置', exact=True).click()
            expect(page.get_by_role('dialog')).to_have_count(0)
            expect(trigger).to_be_focused()
        return 'Esc、取消、保存设置后均回焦到新/原分析设置按钮'

    case('弹窗关闭与保存后的焦点', dialog_focus)

    def task_revision_focus():
        open_fresh('#risks')
        task = page.locator('[data-action="task-detail"][data-id="a04"]')
        task.click()
        dialog = page.get_by_role('dialog')
        choose_option(page, '处理状态', '进行中', scope=dialog)
        dialog.get_by_role('button', name='保存状态', exact=True).click()
        expect(page.get_by_role('dialog')).to_have_count(0)
        expect(task).to_be_focused()
        revision = page.locator('[data-action="revise"][data-id="r13"]')
        revision.click()
        dialog = page.get_by_role('dialog')
        choose_option(page, '生效期间', '2027-07', scope=dialog)
        dialog.get_by_role('spinbutton', name='修订后预算（元）').fill('1890000.00')
        dialog.get_by_role('textbox', name='修订原因').fill('焦点回归验收：核对未来采购假设。')
        dialog.locator('input[name="approved"]').check()
        dialog.get_by_role('button', name='记录演示修订').click()
        expect(page.get_by_role('dialog')).to_have_count(0)
        expect(revision).to_be_focused()
        return '状态保存后回到已移动任务的按钮，预算修订后回到等价修订按钮'

    case('整改与修订保存后的焦点', task_revision_focus)

    def assistant_focus():
        open_fresh('#analysis')
        page.locator('[data-action="detail"][data-id="r01"]').first.click()
        page.get_by_role('dialog').get_by_role('button', name='让助手解释', exact=True).click()
        expect(page.get_by_role('dialog')).to_have_count(0)
        expect(page.locator('#chat-input')).to_be_focused()
        page.wait_for_timeout(600)
        expect(page.locator('#chat-input')).to_be_focused()
        expect(page.locator('#chat-input')).to_have_value('请解释「企业软件许可」的差异原因和处理建议。')
        return '抽屉关闭动画结束后保留助手输入框焦点与问题草稿'

    case('助手显式焦点不被弹窗回焦覆盖', assistant_focus)

    def rapid_operations():
        open_fresh()
        page.evaluate("""() => {
          const select = key => document.querySelector('.sidebar nav [data-page="' + key + '"]').click();
          for (const key of ['analysis','risks','reports','data','history','overview']) select(key);
          const assistant = () => document.querySelector('.topbar [data-action="assistant"]').click();
          for (let i=0;i<6;i++) assistant();
        }""")
        expect(page.get_by_role('heading', name='经营总览', exact=True)).to_be_visible()
        page.wait_for_timeout(850)
        expect(page.locator('.motion-ghost,.liquid-ripple')).to_have_count(0)
        expect(page.locator('.content-layout > .assistant')).to_have_count(0)
        check(page.evaluate("document.querySelector('#main').style.width") == '', '快速切换后主内容残留强制宽度')
        check(page.evaluate("document.getAnimations().length") == 0, '快速切换后残留动画')
        return '连续换页和助手六次切换后无残留幽灵节点、强制宽度或动画'

    case('连续快速操作清理', rapid_operations)

    def layouts():
        checked = 0
        for embedded in [False, True]:
            for width, height in [(1440,1000), (1024,900), (390,844)]:
                page.set_viewport_size({'width':width, 'height':height})
                for key in ['overview','data','analysis','risks','organization','reports','history']:
                    open_fresh(('?embedded=1' if embedded else '') + '#' + key)
                    page.wait_for_timeout(580)
                    dimensions = page.evaluate('({document:document.documentElement.scrollWidth,body:document.body.scrollWidth})')
                    check(dimensions['document'] <= width and dimensions['body'] <= width, f'{embedded}/{width}/{key} 横滚：{dimensions}')
                    check(page.locator('main').bounding_box()['width'] > 0, f'{embedded}/{width}/{key} 主内容隐藏')
                    checked += 1
                if width == 390:
                    open_fresh(('?embedded=1' if embedded else '') + '#risks')
                    page.screenshot(path=str(OUT / f'玻璃-风险移动端-{int(embedded)}.png'), full_page=True, animations='disabled')
        return f'{checked} 个页面尺寸/嵌入组合均无整体横向溢出'

    case('七页多尺寸与嵌入布局', layouts)

    def reduced_motion():
        page.emulate_media(reduced_motion='reduce')
        page.set_viewport_size({'width':1440,'height':1000})
        open_fresh()
        page.locator('.sidebar nav [data-page="risks"]').click()
        page.locator('.sidebar [data-action="settings"]').click()
        check(page.evaluate('document.getAnimations().length') == 0, '减少动态效果时仍有活动动画')
        page.keyboard.press('Escape')
        expect(page.get_by_role('dialog')).to_have_count(0)
        page.locator('.topbar [data-action="assistant"]').click()
        check(page.evaluate('document.getAnimations().length') == 0, '减少动态效果时助手仍有活动动画')
        page.emulate_media(reduced_motion='no-preference')
        return '减少动态效果偏好下换页、弹窗与助手无需动画且可操作'

    case('减少动态效果偏好', reduced_motion)
    case('补充流程浏览器错误', lambda: check(not errors, str(errors)) or '无 console error / pageerror')
    (OUT / ('玻璃焦点回归结果.json' if focus_only else '玻璃回归结果.json')).write_text(json.dumps({'results':results,'browserErrors':errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    browser.close()

raise SystemExit(0 if all(item['passed'] for item in results) else 1)
