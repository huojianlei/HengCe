"""用户级菜单操作：通过按钮与可见选项选择，不操作隐藏 select。"""
from playwright.sync_api import expect


def choose_option(page, label, option_text, scope=None):
    """展开自绘 combobox 并点击可见选项；scope 仅限定触发按钮。

    自绘 combobox 的 aria-label 是“标签：当前值”，因此按标签做子串匹配，
    不能用 exact=True（精确匹配会找不到元素）。
    """
    trigger = (scope or page).get_by_role('combobox', name=label)
    expect(trigger).to_have_attribute('aria-haspopup', 'listbox')
    trigger.click()
    popup = page.get_by_role('listbox')
    expect(popup).to_be_visible()
    popup.get_by_role('option', name=option_text, exact=True).click()
    expect(popup).to_have_count(0)
    expect(trigger).to_contain_text(option_text)


def navigate(page, key):
    """窄屏通过实际展开按钮进入侧栏，再触发目标导航。"""
    menu = page.locator('.mobile-menu')
    if menu.is_visible() and menu.get_attribute('aria-expanded') != 'true':
        menu.click()
    page.locator(f'.sidebar nav [data-page="{key}"]').click()
