"""在独立无头浏览器中验收本地 UI；仅写入验收截图目录。"""
import json
import os
from pathlib import Path
from zipfile import ZipFile

os.environ['TEMP'] = os.environ['TMP'] = 'D:/dev-env/tmp'
from playwright.sync_api import sync_playwright, expect
from 验收辅助 import choose_option, navigate

ROOT = Path(__file__).parent
OUT = ROOT / '验收截图'
OUT.mkdir(exist_ok=True)
URL = 'http://127.0.0.1:4178'
results, errors = [], []


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def case(name, fn):
    try:
        detail = fn()
        results.append({'name': name, 'passed': True, 'detail': detail})
        print('PASS', name, detail or '', flush=True)
    except Exception as exc:
        results.append({'name': name, 'passed': False, 'detail': str(exc)})
        print('FAIL', name, str(exc), flush=True)
        page.screenshot(path=str(OUT / f'失败-{len(results):02d}.png'), full_page=True, animations='disabled')
        page.keyboard.press('Escape')


with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
    page = context.new_page()
    page.set_default_timeout(6000)
    def capture_errors(target, scenario):
        target.on('pageerror', lambda err: errors.append({'type': 'pageerror', 'scenario': scenario, 'message': str(err)}))
        target.on('console', lambda msg: errors.append({'type': 'console', 'scenario': scenario, 'message': msg.text}) if msg.type == 'error' else None)

    capture_errors(page, '完整交互')
    page.goto(URL)
    expect(page.get_by_role('heading', name='经营总览', exact=True)).to_be_visible()

    def nav(key):
        navigate(page, key)

    def navigation():
        page.screenshot(path=str(OUT / '经营总览-1440.png'), full_page=True, animations='disabled')
        pages = [('data', '数据工作区'), ('analysis', '差异分析'), ('risks', '风险与整改'), ('organization', '组织部门'), ('reports', '报告中心'), ('history', '分析记录'), ('overview', '经营总览')]
        for key, title in pages:
            nav(key)
            expect(page.get_by_role('heading', name=title, exact=True)).to_be_visible()
        check(not errors, str(errors))
        return '七页导航成功，未出现 console error 或 pageerror'
    case('七页导航与桌面概览', navigation)

    def filters():
        nav('analysis')
        page.get_by_role('button', name='采购', exact=True).click()
        expect(page.locator('#variance-table tbody tr')).to_have_count(4)
        page.get_by_role('searchbox', name='搜索科目或部门').fill('服务器')
        expect(page.locator('#variance-table tbody tr')).to_have_count(1)
        expect(page.locator('#variance-table')).to_contain_text('生产服务器采购')
        choose_option(page, '筛选预警等级', '正常')
        expect(page.locator('#variance-table')).to_contain_text('没有符合条件')
        choose_option(page, '筛选预警等级', '全部预警等级')
        page.get_by_role('searchbox', name='搜索科目或部门').fill('')
        page.locator('[data-action="module"][data-value="全部"]').click()
        page.screenshot(path=str(OUT / '差异分析-1440.png'), full_page=True, animations='disabled')
        return '模块、关键词、预警筛选均按输入更新'
    case('差异筛选与搜索', filters)

    def settings():
        page.locator('.sidebar [data-action="settings"]').click()
        dialog = page.get_by_role('dialog')
        thresholds = dialog.get_by_role('spinbutton', name='档位阈值百分比')
        thresholds.nth(0).fill('5')
        thresholds.nth(1).fill('10')
        dialog.get_by_role('button', name='保存设置').click()
        expect(page.get_by_role('dialog')).to_have_count(0)
        expect(page.locator('main')).to_contain_text('设置已变更')
        page.locator('main [data-action="run"]').first.click()
        expect(page.get_by_role('progressbar')).to_have_count(0, timeout=8000)
        # 来源中 +9.17% 的云资源成本原为正常，低阈值运行后应进入关注。
        page.get_by_role('searchbox', name='搜索科目或部门').fill('云资源')
        expect(page.locator('#variance-table tbody')).to_contain_text('关注')
        page.get_by_role('searchbox', name='搜索科目或部门').fill('办公设备')
        favorable = page.locator('#variance-table tbody').inner_text()
        check('正常' in favorable, '低阈值分析将有利的采购节省标为风险：' + favorable)
        page.get_by_role('searchbox', name='搜索科目或部门').fill('')
        return '5% / 10% 档位保存并生效，有利差异保持正常'
    case('参数保存与运行分析', settings)

    def tasks():
        nav('risks')
        page.locator('[data-action="task-detail"][data-id="a04"]').click()
        dialog = page.get_by_role('dialog')
        choose_option(page, '处理状态', '进行中', scope=dialog)
        dialog.get_by_role('button', name='保存状态').click()
        expect(page.get_by_role('dialog')).to_have_count(0)
        doing = page.locator('.task-column').nth(1)
        expect(doing).to_contain_text('确认阶段交付排期')
        return '待处理事项移动到进行中'
    case('整改状态变更', tasks)

    def revision():
        page.locator('[data-action="revise"][data-id="r13"]').click()
        dialog = page.get_by_role('dialog')
        choose_option(page, '生效期间', '2027-07', scope=dialog)
        dialog.get_by_role('spinbutton', name='修订后预算（元）').fill('1890000.00')
        dialog.get_by_role('textbox', name='修订原因').fill('验收演示：供应商报价核对完成，调整未来采购假设。')
        dialog.locator('input[name="approved"]').check()
        dialog.get_by_role('button', name='记录演示修订').click()
        expect(page.get_by_role('dialog')).to_have_count(0)
        page.get_by_role('button', name='修订记录', exact=True).click()
        expect(page.get_by_role('dialog')).to_contain_text('2027-07')
        expect(page.get_by_role('dialog')).to_contain_text('1,890,000.00')
        expect(page.get_by_role('dialog')).to_contain_text('验收演示')
        page.keyboard.press('Escape')
        page.screenshot(path=str(OUT / '风险与整改-1440.png'), full_page=True, animations='disabled')
        return '未来期间修订通过人工勾选后记录，保持演示性质'
    case('双环预算修订', revision)

    def reports():
        nav('reports')
        page.get_by_role('button', name='生成本期报告', exact=True).click()
        page.get_by_role('dialog').get_by_role('button', name='生成报告', exact=True).click()
        expect(page.get_by_role('dialog')).to_have_count(0, timeout=8000)
        page.locator('[data-action="export-report"]').first.click()
        saved = []
        for extension, label in [('html', 'HTML 网页'), ('json', 'JSON 数据')]:
            with page.expect_download() as download_info:
                page.get_by_role('dialog').get_by_role('button', name=label, exact=True).click()
            download = download_info.value
            destination = OUT / f'验收导出.{extension}'
            download.save_as(str(destination))
            check(destination.stat().st_size > 200, '下载文件为空')
            saved.append(destination.name)
        exported = json.loads((OUT / '验收导出.json').read_text('utf-8'))
        check(exported['demo'] is True, 'JSON 缺少演示标记')
        check(any(r.get('reason', '').startswith('验收演示') for r in exported['revisions']), 'JSON 未包含当前修订')
        check('演示报告' in (OUT / '验收导出.html').read_text('utf-8'), 'HTML 缺少演示标记')
        page.keyboard.press('Escape')
        page.locator('[data-action="preview-report"]').first.click()
        expect(page.get_by_role('dialog')).to_contain_text('经营分析报告')
        page.screenshot(path=str(OUT / '报告预览-1440.png'), full_page=True, animations='disabled')
        page.keyboard.press('Escape')
        return ' / '.join(saved) + '，预览成功，未调用打印'
    case('报告生成与真实下载', reports)

    def dialog_accessibility():
        page.locator('.sidebar [data-action="settings"]').click()
        dialog = page.get_by_role('dialog')
        controls = dialog.locator('button:not([disabled]):visible,input:visible,select:visible,textarea:visible,a[href]:visible,[tabindex="0"]:visible')
        controls.last.focus()
        page.keyboard.press('Tab')
        check(controls.first.evaluate('(el) => el === document.activeElement'), 'Tab 未从最后一个控件回到第一个控件')
        page.keyboard.press('Shift+Tab')
        check(controls.last.evaluate('(el) => el === document.activeElement'), 'Shift+Tab 未回到最后一个控件')
        page.keyboard.press('Escape')
        expect(dialog).to_have_count(0)
        return 'Tab / Shift+Tab 闭环，Esc 正常关闭'
    case('弹窗键盘操作', dialog_accessibility)

    def local_import():
        nav('data')
        workbook = OUT / '验收-预算基础.xlsx'
        with ZipFile(workbook, 'w') as archive:
            archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/></Types>')
        page.locator('#file-input').set_input_files(str(workbook))
        file_row = page.locator('tbody tr').filter(has_text=workbook.name)
        expect(file_row).to_contain_text('待校验')
        check('项通过' not in file_row.inner_text(), '本地工作簿被假标为校验通过')
        page.locator('main [data-action="run"]').first.click()
        expect(page.get_by_role('status')).to_contain_text('尚未通过后端校验')
        expect(file_row).to_contain_text('待校验')
        page.screenshot(path=str(OUT / '数据待校验-1440.png'), full_page=True, animations='disabled')
        return '本地 xlsx 保持待校验，运行分析明确拒绝'
    case('本地文件导入不假通过', local_import)

    def responsive():
        nav('overview')
        for width, height in [(1024, 900), (390, 844)]:
            page.set_viewport_size({'width': width, 'height': height})
            page.screenshot(path=str(OUT / f'经营总览-{width}.png'), full_page=True, animations='disabled')
            size = page.evaluate('({viewport:innerWidth,document:document.documentElement.scrollWidth,body:document.body.scrollWidth})')
            check(size['document'] <= width and size['body'] <= width, f'{width}px 页面整体横滚：{size}')
        return '1024 / 390 宽布局无整体横向滚动'
    case('响应式布局', responsive)

    def host_failure():
        host_context = browser.new_context(viewport={'width': 1024, 'height': 768})
        host_context.add_init_script("window.hengceHost={version:'1.0', request:async()=>{throw new Error('验收宿主故障：禁止演示回退')}}")
        host_page = host_context.new_page()
        capture_errors(host_page, '宿主错误')
        host_page.goto(URL)
        expect(host_page.get_by_role('heading', name='工作区暂时无法打开')).to_be_visible()
        expect(host_page.locator('body')).to_contain_text('验收宿主故障')
        check(host_page.get_by_role('heading', name='经营总览').count() == 0, '宿主故障错误回退到演示')
        host_context.close()
        return '宿主失败显示错误，不加载演示数据'
    case('宿主错误无演示回退', host_failure)

    # 结构夹具只用于浏览器接入测试。此 stub 不代表 DSH 插件或真实后端。
    fixture_response = context.request.get(URL + '/src/演示数据.mjs')
    check(fixture_response.ok, '无法读取宿主测试的结构夹具')
    fixture_source = fixture_response.text().replace('export function createDemoData', 'function createDemoData')

    def stub_page(name, mutation, suffix=''):
        host_context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        host_context.add_init_script('(() => {\n' + fixture_source + '\n' + """
          const data = createDemoData();
          data.demo = false;
          data.meta.company = '宿主验收公司';
          data.meta.runId = 'host-stub-not-demo';
          window.__hostRequests = [];
        """ + mutation + """
          window.hengceHost = {
            version:'1.0',
            request:async(action, payload) => {
              window.__hostRequests.push({action, payload});
              if (action === 'workspace.load') return structuredClone(data);
              throw new Error('测试 stub 未实现此操作：' + action);
            }
          };
        })();""")
        target = host_context.new_page()
        capture_errors(target, name)
        target.goto(URL + suffix)
        expect(target.get_by_role('heading', name='经营总览', exact=True)).to_be_visible()
        expect(target.locator('.breadcrumb')).to_contain_text('宿主验收公司')
        expect(target.locator('.topbar')).to_contain_text('已连接')
        check(target.locator('.demo-tag').count() == 0, '真实宿主模式错误显示演示标记')
        check(target.evaluate('window.__hostRequests.map(x=>x.action)') == ['workspace.load'], '宿主加载没有通过约定接口')
        return host_context, target

    def host_empty_trend():
        host_context, target = stub_page('宿主空趋势', 'data.trend = [];')
        try:
            expect(target.get_by_role('heading', name='暂无趋势数据', exact=True)).to_be_visible()
            check(target.locator('svg.chart').count() == 0, '空趋势出现伪造图线')
            target.screenshot(path=str(OUT / '宿主空趋势-1440.png'), full_page=True, animations='disabled')
            return 'demo=false 的宿主结构夹具返回空趋势，显示明确空态，无演示曲线回退'
        finally:
            host_context.close()
    case('宿主空趋势不混入演示', host_empty_trend)

    def host_null_actual():
        host_context, target = stub_page('宿主无实际值', 'data.trend.forEach(t => { t.actual = null; });')
        try:
            expect(target.locator('.chart-foot')).to_contain_text('尚无已结账实际数据')
            check(target.locator('svg.chart .chart-point').count() == 0, '缺失实际值显示为实际数据点')
            chart = target.locator('svg.chart').inner_html()
            check('NaN' not in chart and 'Infinity' not in chart, '图表产生无效坐标')
            target.locator('[data-action="trend-detail"]').click()
            rows = target.get_by_role('dialog').locator('tbody tr')
            expect(rows).to_have_count(12)
            for row in rows.all():
                check(row.locator('td').nth(2).inner_text() == '—', '缺失实际值未明确显示为缺失')
            target.screenshot(path=str(OUT / '宿主实际值全缺失-1440.png'), full_page=True, animations='disabled')
            return '实际值全 null 时无实际数据点，12 行明细保持 —，图表无 NaN/Infinity'
        finally:
            host_context.close()
    case('宿主实际收入全缺失', host_null_actual)

    def host_quarter():
        host_context, target = stub_page('宿主季度四点', """
          data.meta.period = data.config.period = '2027-Q2';
          data.config.cycle = '季度';
          data.trend = [
            {period:'2027-Q1',budget:100000000,actual:90000000,rolling:null},
            {period:'2027-Q2',budget:120000000,actual:110000000,rolling:null},
            {period:'2027-Q3',budget:130000000,actual:null,rolling:125000000},
            {period:'2027-Q4',budget:140000000,actual:null,rolling:135000000}
          ];
        """)
        try:
            chart = target.locator('svg.chart')
            check('NaN' not in chart.inner_html() and 'Infinity' not in chart.inner_html(), '季度图表产生无效坐标')
            labels = chart.locator('text').all_text_contents()
            check(all(labels.count(q) == 1 for q in ['Q1', 'Q2', 'Q3', 'Q4']), '季度四点横轴标签不正确')
            expect(chart.locator('.chart-point')).to_have_count(2)
            expect(target.locator('.chart-foot')).to_contain_text('截至 2027-Q2 已结账')
            target.screenshot(path=str(OUT / '宿主季度四点-1440.png'), full_page=True, animations='disabled')
            check('Q2 月' not in target.locator('.page-heading').inner_text(), '季度标题错误显示成 Q2 月')
            return '季度四点显示 Q1—Q4，两个实际点、两个预测点，标题按季度显示'
        finally:
            host_context.close()
    case('宿主季度四点与期间标签', host_quarter)

    def embedded_navigation():
        host_context, target = stub_page('嵌入导航', '', '?embedded=1')
        try:
            expect(target.locator('.sidebar')).not_to_be_visible()
            nav = target.get_by_role('navigation', name='衡策业务导航')
            for key, title in [('data','数据工作区'),('analysis','差异分析'),('risks','风险与整改'),('organization','组织部门'),('reports','报告中心'),('history','分析记录'),('overview','经营总览')]:
                nav.locator(f'[data-page="{key}"]').click()
                expect(target.get_by_role('heading', name=title, exact=True)).to_be_visible()
            nav.get_by_role('button', name='分析设置', exact=True).click()
            expect(target.get_by_role('dialog')).to_contain_text('分析设置')
            target.keyboard.press('Escape')
            target.screenshot(path=str(OUT / '宿主嵌入模式-1440.png'), full_page=True, animations='disabled')
            target.set_viewport_size({'width':390, 'height':844})
            nav.locator('[data-page="history"]').click()
            expect(target.get_by_role('heading', name='分析记录', exact=True)).to_be_visible()
            size = target.evaluate('({viewport:innerWidth,document:document.documentElement.scrollWidth,body:document.body.scrollWidth})')
            check(size['document'] <= 390 and size['body'] <= 390, f'嵌入模式横滚：{size}')
            target.screenshot(path=str(OUT / '宿主嵌入模式-390.png'), full_page=True, animations='disabled')
            return '隐藏侧栏后仍可切换七页与设置，390px 可横向滚动导航且页面不溢出'
        finally:
            host_context.close()
    case('嵌入模式独立导航', embedded_navigation)

    def clean_previews():
        clean_context = browser.new_context(viewport={'width':1440, 'height':1000})
        clean = clean_context.new_page()
        capture_errors(clean, '干净初始截图')
        clean.goto(URL)
        expect(clean.get_by_role('heading', name='经营总览', exact=True)).to_be_visible()
        for key, title in [('overview','经营总览'),('data','数据工作区'),('risks','风险与整改'),('analysis','差异分析'),('reports','报告中心')]:
            clean.locator(f'.sidebar nav [data-page="{key}"]').click()
            expect(clean.get_by_role('heading', name=title, exact=True)).to_be_visible()
            clean.screenshot(path=str(OUT / f'初始-{title}-1440.png'), full_page=True, animations='disabled')
        clean.locator('.sidebar [data-action="settings"]').click()
        expect(clean.get_by_role('dialog')).to_contain_text('分析设置')
        checkbox_width = clean.get_by_role('dialog').locator('input[name="industryCorrection"]').bounding_box()['width']
        check(checkbox_width <= 20, f'行业修正复选框被拉伸：{checkbox_width}px')
        clean.screenshot(path=str(OUT / '初始-分析设置-1440.png'), full_page=True, animations='disabled')
        clean.keyboard.press('Escape')
        clean.locator('.sidebar nav [data-page="overview"]').click()
        clean.locator('.topbar [data-action="assistant"]').click()
        expect(clean.get_by_role('complementary', name='衡策助手')).to_be_visible()
        clean.screenshot(path=str(OUT / '初始-衡策助手-1440.png'), full_page=True, animations='disabled')
        clean.goto(URL + '?embedded=1')
        expect(clean.get_by_role('heading', name='经营总览', exact=True)).to_be_visible()
        clean.screenshot(path=str(OUT / '初始-嵌入模式-1440.png'), full_page=True, animations='disabled')
        clean.goto(URL)
        expect(clean.get_by_role('heading', name='经营总览', exact=True)).to_be_visible()
        for width, height in [(1024,900),(390,844)]:
            clean.set_viewport_size({'width':width, 'height':height})
            if width < 760:
                clean.wait_for_function("document.querySelector('.sidebar').getBoundingClientRect().right <= 0")
            clean.screenshot(path=str(OUT / f'初始-经营总览-{width}.png'), full_page=True, animations='disabled')
        clean_context.close()
        return '已另存未修改参数、状态、文件的初始演示桌面、嵌入、1024、390 截图'
    case('干净初始演示截图', clean_previews)

    case('全流程浏览器错误', lambda: check(not errors, json.dumps(errors, ensure_ascii=False)) or '无 console error / pageerror')
    (OUT / '交互验收结果.json').write_text(json.dumps({'results': results, 'browserErrors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    browser.close()

raise SystemExit(0 if all(result['passed'] for result in results) else 1)
