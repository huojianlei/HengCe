"""验证非线性动效在快速操作、弹窗竞争、减少动态效果与降级时仍可完成。"""
import json
import os
from pathlib import Path

os.environ['TEMP'] = os.environ['TMP'] = 'D:/dev-env/tmp'
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).parent
OUT = ROOT / '验收截图'
URL = 'http://127.0.0.1:4178'
results, errors = [], []

def check(value, message):
    if not value:
        raise AssertionError(message)

def settle(page):
    page.wait_for_function("!document.getAnimations().some(a => a.playState === 'running')")

with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    page.set_default_timeout(6000)
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(URL)
    expect(page.locator('#main')).to_be_visible()
    settle(page)

    def run(name, fn):
        try:
            detail = fn()
            results.append({'name': name, 'passed': True, 'detail': detail})
            print('PASS', name, detail or '', flush=True)
        except Exception as error:
            results.append({'name': name, 'passed': False, 'detail': str(error)})
            print('FAIL', name, str(error), flush=True)

    def page_and_navigation():
        page.locator('.nav-item[data-page="risks"]').click()
        motion = page.evaluate("""() => ({
          main: document.querySelector('#main').getAnimations().map(a => a.effect.getTiming()),
          nav: document.querySelector('.nav-liquid-indicator').getAnimations().map(a => a.effect.getTiming())
        })""")
        check(len(motion['main']) == 1 and len(motion['nav']) == 1, '页面和导航应各有一个进场动画')
        check(motion['main'][0]['duration'] == 480 and motion['nav'][0]['duration'] == 500, '动效时长不一致')
        check(motion['main'][0]['easing'] != 'linear', '页面动效不应为匀速')
        settle(page)
        offsets = page.evaluate("""() => {
          const a = document.querySelector('.nav-item.active').getBoundingClientRect();
          const b = document.querySelector('.nav-liquid-indicator').getBoundingClientRect();
          return [Math.abs(a.x-b.x), Math.abs(a.y-b.y), Math.abs(a.width-b.width)];
        }""")
        check(max(offsets) <= 1.1, f'导航背景未对齐: {offsets}')
        return '页面480ms弹性曲线；导航500ms收敛且落点对齐'
    run('页面与导航非线性切换', page_and_navigation)

    def rapid_navigation():
        page.evaluate("""() => {
          for (const name of ['data','analysis','reports','organization','risks'])
            document.querySelector(`.nav-item[data-page="${name}"]`).click();
        }""")
        settle(page)
        expect(page.locator('#main')).to_have_attribute('data-page', 'risks')
        check(page.locator('.nav-liquid-indicator').count() == 1, '导航背景重复')
        check(page.evaluate('document.getAnimations().length') == 0, '快速切页留下动画')
        return '连续五次切页收敛到最后状态，无残留动画'
    run('快速连续切页', rapid_navigation)

    def same_page():
        page.locator('.nav-item[data-page="analysis"]').click()
        settle(page)
        page.get_by_role('button', name='采购', exact=True).click()
        count = page.evaluate("document.querySelector('#main').getAnimations().length")
        check(count == 0, '同页筛选不应整页重新进场')
        page.get_by_role('searchbox', name='搜索科目或部门').fill('服务器')
        check(page.evaluate("document.activeElement.getAttribute('aria-label')") == '搜索科目或部门', '搜索丢失焦点')
        expect(page.locator('#variance-table tbody tr')).to_have_count(1)
        return '筛选不触发整页动画，搜索保留输入焦点'
    run('同页筛选保持稳定', same_page)

    def assistant():
        before = page.locator('#main').bounding_box()['width']
        page.locator('.topbar [data-action="assistant"]').click()
        page.wait_for_timeout(100)
        middle = page.locator('#main').bounding_box()['width']
        settle(page)
        after = page.locator('#main').bounding_box()['width']
        check(after < middle < before, f'助手宽度没有插值：{before}, {middle}, {after}')
        check(page.evaluate("getComputedStyle(document.querySelector('#main')).transform") == 'none', '主内容不应被缩放')
        page.evaluate("""() => { for (let i=0;i<7;i++) document.querySelector('.topbar [data-action="assistant"]').click(); }""")
        settle(page)
        check(page.locator('.motion-ghost').count() == 0, '关闭助手后留下退出镜像')
        check(page.locator('.content-layout > .assistant').count() == 0, '快速开关后助手状态不正确')
        check(page.evaluate("document.querySelector('#main').style.width") == '', '未恢复主内容宽度')
        check(abs(page.locator('#main').bounding_box()['width'] - before) < 1, '助手关闭后宽度不恢复')
        return f'实际宽度 {before:.0f}→{middle:.1f}→{after:.0f}，连续开关无残留'
    run('助手伸缩与快速开关', assistant)

    def modal_race():
        page.locator('.sidebar [data-action="settings"]').click()
        settle(page)
        page.evaluate("""() => {
          document.querySelector('[data-action="close-dialog"]').click();
          document.querySelector('[data-action="help"]').click();
        }""")
        settle(page)
        expect(page.get_by_role('dialog')).to_be_visible()
        expect(page.locator('#dialog-title')).not_to_have_text('分析设置')
        page.keyboard.press('Escape')
        expect(page.get_by_role('dialog')).to_have_count(0)
        return '旧关闭回调不会清空刚打开的新弹窗'
    run('弹窗关闭与新弹窗竞争', modal_race)

    def reduced_motion():
        page.emulate_media(reduced_motion='reduce')
        page.locator('.nav-item[data-page="overview"]').click()
        check(page.evaluate("document.querySelector('#main').getAnimations().length") == 0, '减少动态效果仍有页面位移')
        page.locator('.sidebar [data-action="settings"]').click()
        check(page.evaluate("document.querySelector('.dialog').getAnimations().length") == 0, '减少动态效果仍有弹窗缩放')
        immediate = page.evaluate("""() => { document.querySelector('[data-action="close-dialog"]').click(); return !document.querySelector('.dialog'); }""")
        check(immediate, '减少动态效果关闭未同步完成')
        page.emulate_media(reduced_motion='no-preference')
        return '系统减少动态效果：无位移/缩放，弹窗同步关闭'
    run('减少动态效果', reduced_motion)

    def fallback():
        page.locator('.sidebar [data-action="settings"]').click()
        settle(page)
        page.evaluate("""() => {
          window.originalAnimate = Element.prototype.animate;
          Element.prototype.animate = () => ({cancel(){}, onfinish:null, oncancel:null});
          document.querySelector('[data-action="close-dialog"]').click();
        }""")
        expect(page.get_by_role('dialog')).to_have_count(0, timeout=1500)
        page.evaluate('() => { Element.prototype.animate = window.originalAnimate; }')
        return '动画完成事件缺失时，限时回退仍关闭弹窗'
    run('动画完成事件缺失的回退', fallback)

    def visual_capture():
        for key, title in [('overview','经营总览'),('risks','风险与整改')]:
            page.locator(f'.nav-item[data-page="{key}"]').click()
            settle(page)
            page.screenshot(path=str(OUT / f'玻璃版-{title}-1440.png'), full_page=True)
        page.locator('.topbar [data-action="assistant"]').click()
        settle(page)
        page.screenshot(path=str(OUT / '玻璃版-助手-1440.png'), full_page=True)
        page.locator('.sidebar [data-action="settings"]').click()
        settle(page)
        page.screenshot(path=str(OUT / '玻璃版-分析设置-1440.png'))
        page.keyboard.press('Escape')
        expect(page.get_by_role('dialog')).to_have_count(0)
        return '已保存四张改版截图'
    run('最终视觉留档', visual_capture)
    check(not errors, f'浏览器异常: {errors}')
    browser.close()

(OUT / '动效验收结果.json').write_text(json.dumps({'results': results, 'errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
passed = sum(result['passed'] for result in results)
print(f'{passed}/{len(results)} passed', flush=True)
raise SystemExit(0 if passed == len(results) and not errors else 1)

