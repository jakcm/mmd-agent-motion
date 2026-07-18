# MMD 模型查看器

基于 Three.js 的移动端 MMD 模型查看器，支持 PMX/PMD 模型加载、VMD 舞蹈动画、音频同步播放、唇形同步等功能。

## 功能

- 支持 PMX/PMD 3D 模型加载
- 支持 VMD 舞蹈动画播放
- 音频与动画同步播放
- 待机 idle 动画循环
- Edge TTS 唇形同步
- 移动端触控操作（单指旋转、双指缩放平移）
- OutlineEffect 描边渲染
- 本地文件导入（模型/舞蹈/音频）
- 渲染参数实时调节

## 技术参考

- [MMDLoader-app](https://github.com/takahirox/MMDLoader-app) — Three.js MMD 模型加载器示例
- [Three.js MMDLoader](https://threejs.org/docs/#examples/en/loaders/MMDLoader) — Three.js 官方 MMD 加载器文档

## 技术栈

- [Three.js](https://threejs.org/) v0.171.0（MMDLoader 最后支持版本）
- Edge TTS 语音合成
- GitHub Pages 部署

## 部署前必做

每次推送到 GitHub 前，请手动更新版本号：

1. **修改加载 loading 界面的版本号** — `index.html` 中的 `BUILD_TIMESTAMP`
2. **修改模型选择弹窗界面左上角版本号** — 与上述使用同一变量，自动同步
3. **版本号格式**：`Version: yyyyMMddHHmm`
4. **以开始推送 GitHub 时的北京时间（+8 时区）为准**
5. 定位到 `index.html` 中的以下代码块：

```javascript
// ===== 构建版本号（yyyyMMddHHmm，推送 GitHub 时更新，北京时间 +8） =====
const BUILD_TIMESTAMP = 'Version: 202607182244'; // 每次推送前手动更新
```

将 `202607182244` 替换为当前北京时间即可运行 `TZ='Asia/Shanghai' date '+%Y%m%d%H%M'` 生成。

## 部署

```bash
# 推送到 GitHub 自动部署到 GitHub Pages
git push origin main
```

## 许可

仅用于个人学习和研究。