# 69shuba-novel-Downloader

# 69书吧小说下载器 - 完整使用指南

## 📦 依赖安装

```bash
pip install selenium beautifulsoup4 tqdm ebooklib
```

## 🚀 本地使用

### 1. 安装ChromeDriver

**方法一：自动安装（推荐）**
```bash
pip install webdriver-manager
```

然后修改代码中的driver创建部分：
```python
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)
```

**方法二：手动安装**
- 下载地址: https://chromedriver.chromium.org/
- 确保ChromeDriver版本与Chrome浏览器版本匹配
- 将ChromeDriver放在系统PATH中

### 2. 运行下载器

```bash
python shuba_downloader.py
```

### 3. 使用步骤

1. **输入线程数**（默认1，推荐1-3）
2. **输入书籍ID**（从URL中获取，如 `12345`）
3. **选择保存路径**（默认当前目录）
4. **选择下载模式**：
   - 1: 下载全部章节 (txt格式)
   - 2: 下载全部章节 (epub格式)
   - 3: 指定章节范围下载

### 4. 断点续传

程序会自动保存下载进度到 `download_status.json`，下次运行会询问是否继续下载。

---


## 📋 功能特性

✅ **单文件实现** - 所有功能集成在一个Python文件中  
✅ **Selenium驱动** - 模拟浏览器环境  
✅ **断点续传** - 自动保存下载进度  
✅ **多线程下载** - 支持1-3个线程（默认1）  
✅ **章节范围** - 支持指定起始和结束章节  
✅ **双格式导出** - 支持txt和epub格式  
✅ **GitHub Actions** - 可部署到云端自动下载  
✅ **错误重试** - 失败自动重试3次  
✅ **优雅退出** - Ctrl+C中断会保存已下载内容  

---

## ⚠️ 注意事项

1. **线程数建议**: 设置为1可避免触发反爬虫，设置为2-3可加快速度但有风险
2. **下载间隔**: 程序已内置延迟，无需额外等待
3. **ChromeDriver版本**: 必须与Chrome浏览器版本匹配
4. **网络问题**: 如遇连接失败，程序会自动重试3次
5. **合法使用**: 仅供学习交流，请勿用于商业用途

---

## 📝 示例

### 本地下载全本
```bash
python shuba_downloader.py
# 输入书籍ID: 12345
# 选择: 1 (txt格式)
```

### 下载指定章节
```bash
python shuba_downloader.py
# 输入书籍ID: 12345
# 选择: 3 (指定范围)
# 起始章节: 1
# 结束章节: 100
# 格式: txt
```

---
