# -*- coding: utf-8 -*-
"""verify_v11 —— 1.1.1 总验收一条命令（v1.2：随演示生成器就地运行）。

链路（六阶段）：
    ① 生成四文件（演示生成器 v1.2：三表两列制 + 缓存完备 + 主体企业化）；
    ② ingest_v11 全绿：生成器自验收 verify.py 全项 + ingest_v11 测试套件
       （老 226 项 + 新区校验 + v1.2 新轨用例全过）；
    ③ 老底稿兼容实测：experimental 老底稿经双轨导入器老轨道照进 226；
    ④ 计算报告生成与结构断言：九个模块章节各有三段（数据表/分析内容/
       依据条例）、『AI 分析解读』章节在位且唯一、幂等复跑不重复
       （compute_report_pipeline 同输入逐字节一致 + zhuijie_jiedu 跳过）；
    ⑤ 密度抽查（分录笔数/新区恒等式计数/EPS）；
    ⑥ 打印验收摘要（非零退出码 = 有失败项）。
用法：python D:/AppProject/开发分支_1.1.1/演示生成器/verify_v11.py
     （路径锚定为探测式：本文件无论放在 1.1.1 根还是 演示生成器/ 下均可运行）
建立：2026-10-11 ｜ Agent：ZCode（GLM-5.3）｜ v1.2 迁入演示生成器：2026-10-16
"""
import subprocess  # 子进程跑 verify.py / unittest
import sys  # 路径引导
from pathlib import Path  # 契约/导入器/报告目录

BEN_MU = Path(__file__).resolve().parent             # 本文件所在目录
# 探测式锚定：所在目录含 ingest_v11 = 1.1.1 根；否则取上级（本文件现居 演示生成器/）
GEN_MU = BEN_MU if (BEN_MU / 'ingest_v11').exists() else BEN_MU.parent  # 1.1.1 根
YANSHI_MU = GEN_MU / '演示生成器'                    # 演示生成器目录
INGEST_MU = GEN_MU / 'ingest_v11'                   # 契约/导入器目录
BAOGAO_MU = GEN_MU / '报告组装'                      # 报告流水线目录
DIGAO_105 = Path(r'D:\AppProject\开发分支_1.0.5\desktop\experimental\演示底稿-预算基础.xlsx')  # 老底稿（只读）
SEED = 20260923  # 固定种子（与演示生成器 verify.py 同源）

sys.path.insert(0, str(YANSHI_MU))                  # 企业名生成（demo_model）
from demo_model import qiye_ming                    # noqa: E402  主体企业化命名

ENTITY = qiye_ming(SEED)                            # 企业主体（v1.2 随机生成）
PASSED, FAILED = [], []                             # 验收双清单


def check(name, ok, detail=''):  # 登记并打印
    """登记并打印单项验收结果。"""
    (PASSED if ok else FAILED).append(f'{name}{("：" + detail) if detail else ""}')  # 结果分箱
    print(f'  [{"PASS" if ok else "FAIL"}] {name}' + (f'：{detail}' if detail else ''))
    return ok


def jieduan_yanshiqi():  # 跑生成器自验收（v1.2 全项）
    """阶段①②前置：跑演示生成器自验收（生成四文件 + 结构 + excel_ingest_v11 + v1.2 专项）。"""
    print('== 阶段①② 演示生成器自验收（生成四文件 + 结构 + excel_ingest_v11 + v1.2 专项） ==')  # 子进程跑 verify.py
    r = subprocess.run([sys.executable, '-B', str(YANSHI_MU / 'verify.py')],
                       cwd=str(YANSHI_MU), capture_output=True, text=True,  # 摘取关键行做详情
                       encoding='utf-8', errors='replace', timeout=1200)  # 退出码 0 = 全绿
    wei = [h for h in r.stdout.splitlines() if h.startswith('====') or '通过' in h][:2]
    check('演示生成器 verify.py 全项全绿（v1.2）', r.returncode == 0, '；'.join(wei))


def jieduan_ingest_ceshi():  # 跑 ingest_v11 套件
    """阶段②：ingest_v11 测试套件（老底稿照进/零漂移/骨架/激活/拒收/v1.2 新轨）。"""
    print('== 阶段② ingest_v11 测试套件 ==')  # 子进程 unittest discover
    r = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'discover',
                        '-s', 'tests', '-t', '.'],
                       cwd=str(INGEST_MU), capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=1200)  # unittest 结果在 stderr
    shu_chu = r.stdout + r.stderr  # returncode + OK 双判
    ok = r.returncode == 0 and 'OK' in shu_chu  # 取 Ran 行做详情
    check('ingest_v11 测试套件全绿（v1.1 老轨 + v1.2 新轨）', ok,
          next((h for h in shu_chu.splitlines() if 'Ran ' in h), ''))


def jieduan_lao_di_gao():  # 挂导入器路径
    """阶段③：老底稿兼容实测（experimental 老底稿经双轨导入器老轨道照进 226）。"""
    print('== 阶段③ 老底稿兼容实测（双轨老轨道） ==')  # v1.2 双轨严格导入器
    sys.path.insert(0, str(INGEST_MU))
    from excel_ingest_v11 import import_excel_v11   # v1.2 双轨严格导入器
    r = import_excel_v11(DIGAO_105.read_bytes(), '演示底稿-预算基础.xlsx')  # 老区 226 + 新区不激活
    check('老底稿（experimental）照进：老区 226 全过、老轨道、新区不激活',  # 详情带计数
          r['checks'] == 226 and r['zone_checks'] == 0 and r['zones'] == {}
          and r['contract_version'] == 'v1.1',
          f"checks={r['checks']} zone_checks={r['zone_checks']} ver={r['contract_version']}")  # 返回导入器供后续阶段
    return import_excel_v11                        # 复用给阶段④⑤


def jieduan_baogao(dao_ru):  # 挂报告/生成器路径
    """阶段④：计算报告生成 + 结构断言 + 幂等复跑（报告组装主链）。"""
    print('== 阶段④ 计算报告-月度（三段式 + AI 解读 + 幂等） ==')
    sys.path.insert(0, str(BAOGAO_MU))  # 报告流水线（自动挂 algo 路径）
    sys.path.insert(0, str(YANSHI_MU))  # 合并与输入装配（1.0.5 只读复用）
    import baogao_liuxian as bl                    # 报告流水线（自动挂 algo/houtai 路径）
    from excel_generate import combine_imports, demo_input   # 合并/输入装配（只读复用）
    from yinqing import fenxi                      # 编排层十五步主链
    shu_chu = YANSHI_MU / '输出'  # 逐类读入生成文件
    items = []
    for k in ('预算基础', '实时经营', '行业对标', '经营变更'):  # 四类合并 → fenxi 输入装配 → 全链分析
        ming = f'演示-{k}-{ENTITY}-{SEED}.xlsx'      # v1.2 企业主体文件名
        items.append(dao_ru((shu_chu / ming).read_bytes(), ming))  # 判定行数>0 即跑通
    jieguo = fenxi(demo_input(combine_imports(items)))
    check('分析主链 fenxi() 跑通（十五步）', len(jieguo['decisions']) > 0,
          f"判定 {len(jieguo['decisions'])} 行 / 整改 {len(jieguo['correction'].qingdan)} 条")  # 真kb2 检索（numpy+onnx 齐备）
    r = bl.compute_report_pipeline(jieguo)         # 真kb2 检索（本机 numpy+onnx 齐备）
    md_lu = Path(r['md'])
    md = md_lu.read_text(encoding='utf-8')  # md 存在性与规模
    check('计算报告-月度.md 生成', md_lu.exists(), f'{len(md)} 字符 / 出处 {r["tiaoli_shu"]} 条')
    # 结构断言：逐章节切分，每章三段齐（数据表/分析内容/依据条例）
    zhang = [z for z in md.split('\n## ') if z.startswith('模块')]
    san_duan = [z for z in zhang if '**数据表**' in z and '**分析内容**' in z
                and '**依据条例' in z]
    check('模块章节各含三段（数据表/分析内容/依据条例）', len(zhang) >= 4 and len(san_duan) == len(zhang),  # 每章三段标记齐
          f'{len(san_duan)}/{len(zhang)} 章')
    check('AI 分析解读章节在位且唯一', md.count('## AI 分析解读') == 1
          and '### 总体解读' in md and '### 逐条整改建议' in md)
    check('占位文案标注 DSH 回填口径', '确定性占位' in md and 'DSH 宿主 agent' in md)
    # 幂等复跑：同输入重建逐字节一致（不重复贴解读）
    qian = md_lu.read_bytes()
    bl.compute_report_pipeline(jieguo)  # 占位标注在文内
    check('幂等复跑不重复（同输入逐字节一致）', md_lu.read_bytes() == qian)
    check('追加解读幂等跳过（pipeline_m5 纪律）',
          bl.zhuijie_jiedu(str(md_lu), '测试段') is False)  # 幂等：同输入重建逐字节一致
    # HTML 版同步
    htm = Path(r['html']).read_text(encoding='utf-8')  # 追加纪律：已含即跳过
    check('HTML 版同步生成（含表格与解读章节）',
          htm.startswith('<!DOCTYPE html>') and '<table>' in htm and 'AI 分析解读' in htm,
          f'{len(htm)} 字符')  # HTML 同步产物
    # 依据条例真实检索证据（kb2 只读引用命中即有出处行）
    check('依据条例为 kb2 真检索（出处行含指引号定位）', '**出处 ' in md and '-P' not in md.split('**出处 ')[1][:40])
    return jieguo
  # 出处行可解析


def jieduan_mido(dao_ru):  # 返回分析结果
    """阶段⑤：密度抽查（分录笔数/新区恒等式计数/EPS——对生成文件复核）。"""
    print('== 阶段⑤ 密度抽查 ==')
    shu_chu = YANSHI_MU / '输出'
    yuqi = {'预算基础': (111, 108), '实时经营': (63, 54)}  # 密度预期表（v1.2 企业主体文件名）
    for k, (zc, fl) in yuqi.items():
        ming = f'演示-{k}-{ENTITY}-{SEED}.xlsx'
        r = dao_ru((shu_chu / ming).read_bytes(), ming)
        check(f'[{k}] 密度：新区恒等式 {zc} 项 / 分录 {fl} 笔 / 五区齐',
              r['zone_checks'] == zc  # 逐类别读入复核
              and len(r['zones']['fenlu_quanzhang']['fentiao']) == fl
              and len(r['zones']) == 5,  # 恒等式计数 + 分录笔数 + 五区齐
              f"zone_checks={r['zone_checks']}")
        check(f'[{k}] EPS 为正（披露口径）', r['zones']['lirun_buchong']['eps_jicheng'] > 0)


def main():  # EPS 为正
    """总验收主链：六阶段 → 摘要（退出码承载结果）。"""
    jieduan_yanshiqi()
    jieduan_ingest_ceshi()
    dao_ru = jieduan_lao_di_gao()  # 主链：六阶段→摘要
    jieduan_baogao(dao_ru)
    jieduan_mido(dao_ru)
    print()
    print('==== verify_v11 验收摘要 ====')
    print(f'通过 {len(PASSED)} 项，失败 {len(FAILED)} 项')
    for f in FAILED:
        print('  FAIL:', f)  # 退出码承载结果
    for p in PASSED:
        print('  PASS', p)
    return 0 if not FAILED else 1


if __name__ == '__main__':
    sys.exit(main())
