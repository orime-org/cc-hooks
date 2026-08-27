# 脚本用法和输出

两个脚本：`extract-tokens.js` 在 node 下扫源码拿 CSS 变量名，`inject-collect.js` 注入页面把它们解析成值并采一份聚合数据。

值的归一化全部由 CSS 引擎做 —— `#2563eb`、`hsl()`、`oklch()`、`1rem`、`var()` 链都落到同一表示法。不要手写换算。

## 1. 跑

```bash
node scripts/extract-tokens.js . > /tmp/va-tokens.json

NAMES=$(node -e 'console.log(JSON.stringify(require("/tmp/va-tokens.json").tokens.map(t=>t.name)))')
sed "s|CONFIG|{\"tokens\":$NAMES}|" \
  "scripts/inject-collect.js" > /tmp/va-inject.js
```

把 `/tmp/va-inject.js` 交给浏览器驱动执行。原样注入会抛 `ReferenceError: CONFIG is not defined`。

`CONFIG` 可选字段：`rootSelector`（默认 `body`，页面太大时缩到改动的子树）、`limit`（默认 1500）。

## 2. extract-tokens.js 的输出

```json
{
  "tokenCount": 64,
  "tokens": [{ "name": "--color-primary", "sources": ["src/styles/tokens.css"] }],
  "truncated": false,
  "truncatedBy": null,
  "tailwindConfig": null,
  "note": null
}
```

`tokenCount` 为 0 且 `truncated` 为 false 且无 `tailwindConfig` —— 项目没有 token 定义，跳过 token 那部分。

`truncated` 为 true —— 扫描触顶（文件 2000 或深度 12），结果不完整，缩小范围重扫，别当成「没有 token」。

`tailwindConfig` 非 null —— scale 在 config 对象里，需要另行提供。

## 3. inject-collect.js 的输出

```json
{
  "url": "http://localhost:3000/settings",
  "viewport": { "w": 1440, "h": 900 },
  "sampled": 312,
  "truncated": false,
  "unreachable": { "shadowRoots": 0, "frames": 1 },

  "tokens": {
    "resolved": 58, "total": 64, "ratios": [1.5, 1.25],
    "list": [{ "name": "--color-primary", "declared": "#2563eb", "kind": "color", "value": "rgb(37, 99, 235)" }]
  },

  "used": {
    "color": ["rgb(17, 17, 17)", "rgb(37, 99, 235)"],
    "fontSize": ["14px", "16px", "24px"],
    "spacing": ["8px", "13px", "16px"],
    "radius": ["6px", "7px"]
  },

  "offToken": {
    "color": [{ "value": "rgb(37, 99, 236)", "count": 1, "sample": ["button.btn-primary"] }],
    "spacing": [{ "value": "13px", "count": 4, "sample": ["div.card", "div.card:nth-of-type(2)"] }]
  },

  "checks": {
    "contrast": [{ "sel": "span.hint", "ratio": 3.8, "need": 4.5, "fontSize": "14px", "color": "rgba(0,0,0,0.45)", "bg": "rgb(255, 255, 255)" }],
    "contrastUnknown": [{ "sel": "div.hero h1", "color": "rgb(255, 255, 255)", "reason": "backdrop is an image or gradient" }],
    "targets": [{ "sel": "button.icon", "w": 20, "h": 20 }],
    "clipped": [{ "sel": "div.table-wrap", "scrollWidth": 1100, "clientWidth": 900 }],
    "documentOverflowX": false,
    "viewportUserScalable": true
  }
}
```

| 字段 | 说明 |
|---|---|
| `used` | 页面实际用到的值，去重排序。看一眼就知道这个页面有几种字号、几种间距 |
| `offToken` | `used` 里不在 token 集合中的，带出现次数和几个样例选择器。`count` 是这份样本里的出现数，不是全站的 |
| `tokens.ratios` | 无单位的比值 token（行高那类）。它们跟元素的 px 计算值不可能直接相等，所以不参与 `offToken` 判定 |
| `tokens.list[].kind` | `color` / `length` / `weight` / `family` / `shadow` / `ratio` / `unresolved`。`unresolved` 是源码里声明了但这个页面上解析不出值 |
| `checks.contrast` | 半透明前景先按背景合成再取比值 |
| `checks.contrastUnknown` | **非空说明有元素测不了**，那部分没有结论，别当成通过 |
| `checks.targets` | 小于 24×24 的可交互元素。父元素带自己正文的（句子里的链接）已按 WCAG 的 Inline 例外排除；`<a><svg/></a>` 这类图标链接不属于例外 |
| `truncated` | 可见元素超过 `limit`。用 `rootSelector` 缩小重取 |
| `unreachable` | shadow root 和 frame 的数量，它们内部的样式够不着。非零时在报告里写明这部分没查 |

## 4. 几件已知的事

**UA 默认样式没有单独过滤**。`used` 里会有浏览器给的字号和边框，它们同样出现在 `offToken` 里。判断哪些是作者写的、哪些是浏览器给的，看截图比看数据快。

**第三方组件库的内部样式会进 `used`**。Ant Design、MUI 这类会带来大量自己的值。`offToken` 里 `count` 高又集中在同一组选择器前缀的，多半是库自己的。

**`em` 单位的间距会随字号变化**，同一条声明在不同字号下算出不同像素值。看到 `offToken.spacing` 里有奇怪的小数，先想想是不是这个。

## 5. 测试

```bash
python3 watcher/tests/smoke-visual-adversary.py
```

`extract-tokens.js` 的断言用临时目录造 fixture；`inject-collect.js` 的断言由 `watcher/tests/va-browser-check.js` 在真实 chromium 里跑。

playwright 从全局 `@playwright/mcp` 的依赖解析。pin 的 chromium 不在缓存时回退到缓存里最新的 headless shell，只在报错是 `Executable doesn't exist` 时回退。playwright 找不到退出码 2，smoke 判失败。

改完脚本确认测试有效的办法：把某处修复临时去掉，重跑，看对应断言变红再恢复。
