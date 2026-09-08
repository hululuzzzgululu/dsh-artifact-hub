# share-web

Artifact Hub 的独立公开分享前端。它只生成静态资源，不包含独立 Web 服务；生产环境由 Artifact Hub 前面的 Nginx 托管。

## 开发

先在 `hub/` 启动 Artifact Hub（默认端口 `8000`），再运行：

```bash
cd apps/share-web
pnpm install
pnpm dev
```

Vite 会把 `/api` 代理到本地 Hub。打开一个真实分享地址，例如 `http://127.0.0.1:5173/s/{token}`。

如果前端与 Hub 不同源，可在构建时设置 `VITE_API_BASE_URL`。生产环境建议保持同源，由 Nginx 反向代理 `/api/`。

## 构建

```bash
pnpm build
```

构建结果位于 `dist/`。将其中内容复制到 Nginx 的 share-web 静态目录，并使用仓库 `deploy/nginx/share-web.conf` 中的路由规则。

公开页面支持 Markdown、JSON、常见编程语言与配置文件（按 MIME 或扩展名识别并显示行号、语法高亮）、图片、PDF 和沙箱 HTML 预览。代码类型包括 Python、SQL、JavaScript/TypeScript、Java、Go、Rust、C/C++、C#、Kotlin、Swift、Shell、CSS、XML、YAML、GraphQL 等。未知格式提供下载；所有分享均允许查看和下载。
