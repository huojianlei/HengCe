// 重建 node_modules/@deepseek-ai 下的 junction 链接（树外插件解析 dsh 官方包的唯一通道）。
// 幂等：已存在则先删后建。Node fs.symlinkSync(junction) 无需管理员权限。
// 依据 2026-09-05 实测：junction 指向 harness 编译产物（lib/index.js），树外 import 即可解析。
const fs = require('fs')
const path = require('path')

const 插件根 = path.resolve(__dirname, '..')
const 作用域目录 = path.join(插件根, 'node_modules', '@deepseek-ai')

// 包名 → harness 内真实包目录（只读引用，绝不写入）
const 链接表 = [
  ['dsh-tools', 'D:/AppProject/harness/packages/core/tools'],
  ['cordis', 'D:/AppProject/harness/vendor/cordis'],
]

fs.mkdirSync(作用域目录, { recursive: true })
for (const [包名, 目标] of 链接表) {
  const 链接路径 = path.join(作用域目录, 包名)
  try { fs.rmSync(链接路径, { recursive: true, force: true }) } catch {}
  fs.symlinkSync(目标, 链接路径, 'junction')
  console.log('junction', '@deepseek-ai/' + 包名, '->', fs.readlinkSync(链接路径))
}
console.log('完成：', 链接表.length, '个链接')
