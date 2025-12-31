#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
书吧小说下载器
支持txt和epub格式导出
使用Selenium模拟浏览器
"""

import os
import sys
import time
import json
import re
import signal
import atexit
import threading
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
except ImportError:
    print("错误: 请先安装 selenium")
    print("运行: pip install selenium")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("错误: 请先安装 beautifulsoup4")
    print("运行: pip install beautifulsoup4")
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    print("错误: 请先安装 tqdm")
    print("运行: pip install tqdm")
    sys.exit(1)

# 全局配置
CONFIG = {
    "max_workers": 1,
    "page_timeout": 20,
    "status_file": "download_status.json",
    "base_url": "https://www.69shuba.com",
    "retry_times": 3,
    "retry_delay": 2,
}

# 全局变量
print_lock = threading.Lock()
driver_pool = []
driver_lock = threading.Lock()
stop_flag = threading.Event()  # 全局停止标志


def safe_print(msg: str):
    """线程安全的打印"""
    with print_lock:
        print(msg, flush=True)  # 强制刷新缓冲区


def create_driver() -> webdriver.Chrome:
    """创建Chrome浏览器实例"""
    safe_print("正在创建Chrome浏览器实例...")

    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-software-rasterizer')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-logging')
    options.add_argument('--log-level=3')
    options.add_argument('--silent')
    options.add_argument(
        'user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36')

    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option('useAutomationExtension', False)

    # GitHub Actions 环境特殊配置
    if os.environ.get('CI'):
        safe_print("检测到 CI 环境，应用特殊配置...")
        options.add_argument('--disable-setuid-sandbox')
        options.add_argument('--single-process')

    try:
        safe_print("正在启动 ChromeDriver...")
        driver = webdriver.Chrome(options=options)
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        })
        driver.set_page_load_timeout(CONFIG["page_timeout"])
        safe_print("✓ Chrome浏览器实例创建成功")
        return driver
    except Exception as e:
        safe_print(f"✗ 创建浏览器失败: {e}")
        safe_print("提示: 请确保已安装Chrome浏览器和ChromeDriver")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def get_driver() -> webdriver.Chrome:
    """从池中获取或创建driver"""
    with driver_lock:
        if driver_pool:
            return driver_pool.pop()
        return create_driver()


def return_driver(driver: webdriver.Chrome):
    """归还driver到池"""
    with driver_lock:
        driver_pool.append(driver)


def close_all_drivers():
    """关闭所有driver"""
    with driver_lock:
        for driver in driver_pool:
            try:
                driver.quit()
            except:
                pass
        driver_pool.clear()


atexit.register(close_all_drivers)


def fetch_page_with_selenium(url: str, wait_element: Optional[str] = None) -> str:
    """使用Selenium获取页面内容"""
    driver = get_driver()
    try:
        safe_print(f"正在访问: {url}")
        driver.get(url)

        if wait_element:
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, wait_element))
                )
                safe_print(f"✓ 页面元素加载完成")
            except TimeoutException:
                safe_print(f"⚠ 等待元素超时，继续处理...")

        time.sleep(1)
        html = driver.page_source
        safe_print(f"✓ 页面内容获取成功 (长度: {len(html)})")
        return html
    except Exception as e:
        safe_print(f"✗ 访问 {url} 失败: {e}")
        return ""
    finally:
        return_driver(driver)


def get_book_info(book_id: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """获取书籍信息: 书名、作者、简介"""
    url = f"{CONFIG['base_url']}/book/{book_id}.htm"
    safe_print(f"正在获取书籍信息: {url}")

    html = fetch_page_with_selenium(url, ".booknav2")
    if not html:
        return None, None, None

    soup = BeautifulSoup(html, 'html.parser')

    name = "未知书名"
    name_element = soup.select_one('.booknav2 h1')
    if name_element:
        author_tag = name_element.find('small')
        if author_tag:
            author_tag.extract()
        name = name_element.text.strip()

    author = "未知作者"
    author_element = soup.select_one('.booknav2 p')
    if author_element:
        author_text = author_element.text.strip()
        author = author_text.replace('作者：', '').strip()

    description = "暂无简介"
    desc_element = soup.select_one('.navtxt p')
    if desc_element:
        description = desc_element.text.strip()

    safe_print(f"书籍信息: {name} / {author}")
    return name, author, description


def get_chapter_list(book_id: str) -> List[Dict]:
    """获取章节列表"""
    url = f"{CONFIG['base_url']}/book/{book_id}/"
    safe_print(f"正在获取章节列表...")

    html = fetch_page_with_selenium(url, ".catalog")
    if not html:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    chapters = []

    chapter_links = []
    chapter_links = soup.select('.catalog ul li a')

    if not chapter_links:
        chapter_links = soup.select('.listmain dd a')

    if not chapter_links:
        chapter_links = soup.select('#list dl dd a')

    if not chapter_links:
        chapter_links = soup.select('.chapterlist a')

    if not chapter_links:
        chapter_links = soup.select('a[href*="/txt/"]')

    for idx, link in enumerate(chapter_links):
        title = link.text.strip()
        href = link.get('href', '')

        if href and title:
            if href.startswith('http'):
                chapter_url = href
            elif href.startswith('/'):
                chapter_url = f"{CONFIG['base_url']}{href}"
            else:
                chapter_url = f"{CONFIG['base_url']}/{href}"

            chapter_id = href.rstrip('.html').split('/')[-1]

            chapters.append({
                "id": chapter_id,
                "title": title,
                "url": chapter_url,
                "index": idx
            })

    safe_print(f"共找到 {len(chapters)} 章")
    return chapters


def get_chapter_content(chapter: Dict) -> Optional[str]:
    """获取单章内容"""
    for attempt in range(CONFIG["retry_times"]):
        if stop_flag.is_set():  # 检查停止标志
            return None

        try:
            html = fetch_page_with_selenium(chapter["url"], ".txtnav")
            if not html:
                time.sleep(CONFIG["retry_delay"])
                continue

            soup = BeautifulSoup(html, 'html.parser')

            content_div = None
            content_div = soup.select_one('.txtnav')

            if not content_div:
                content_div = soup.select_one('#content')

            if not content_div:
                content_div = soup.select_one('.content')

            if not content_div:
                content_div = soup.select_one('#txtContent')

            if not content_div:
                safe_print(f"未找到章节内容: {chapter['title']}")
                time.sleep(CONFIG["retry_delay"])
                continue

            paragraphs = []

            for tag in content_div.find_all(['script', 'style']):
                tag.decompose()

            for tag in content_div.find_all(['div', 'p'], class_=['readinline', 'readpage', 'readpage2']):
                tag.decompose()

            chapter_title = chapter['title'].strip()
            title_seen_count = 0

            for element in content_div.stripped_strings:
                text = element.strip()

                if text == chapter_title or text.startswith(chapter_title):
                    title_seen_count += 1
                    if title_seen_count > 1:
                        continue

                if re.match(r'^\d{4}-\d{2}-\d{2}$', text):
                    continue

                if text.startswith('作者：') or text.startswith('作者:'):
                    continue

                if text and not any(skip in text for skip in [
                    '章节错误', '举报', '加入书签', 'www.69shuba.com',
                    '69书吧', '请记住本站', '本章未完', '点击下一页',
                    '()', '(本章完)', '手机用户请浏览', '更好的阅读体验',
                    '最新网址', '最新章节', '手机阅读'
                ]):
                    paragraphs.append(text)

            if paragraphs:
                content = "\n".join(paragraphs)
                return content

            time.sleep(CONFIG["retry_delay"])

        except Exception as e:
            safe_print(f"获取章节 {chapter['title']} 失败: {e}")
            if attempt < CONFIG["retry_times"] - 1:
                time.sleep(CONFIG["retry_delay"])
            continue

    return None


def process_chapter_content(content: str) -> str:
    """处理章节内容"""
    if not content:
        return ""

    content = re.sub(r'<[^>]+>', '', content)
    content = content.replace('\r', '')
    content = re.sub(r'\n{4,}', '\n\n', content)

    lines = content.split('\n')
    cleaned_lines = [line.strip() for line in lines]
    content = '\n'.join(cleaned_lines)

    return content.strip()


def load_status(save_path: str) -> set:
    """加载下载状态"""
    status_file = os.path.join(save_path, CONFIG["status_file"])
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return set(data)
        except:
            pass
    return set()


def save_status(save_path: str, downloaded: set):
    """保存下载状态"""
    status_file = os.path.join(save_path, CONFIG["status_file"])
    try:
        with open(status_file, 'w', encoding='utf-8') as f:
            json.dump(list(downloaded), f, ensure_ascii=False, indent=2)
    except Exception as e:
        safe_print(f"保存状态失败: {e}")


def save_as_txt(output_path: str, book_name: str, author: str, description: str,
                chapter_results: Dict, chapters: List[Dict]):
    """保存为TXT格式"""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"书名: {book_name}\n")
            f.write(f"作者: {author}\n")
            f.write(f"简介: {description}\n")
            f.write(f"\n{'=' * 50}\n\n")

            for idx in sorted(chapter_results.keys()):
                result = chapter_results[idx]

                f.write(f"{result['title']}\n\n")

                content = result['content']
                lines = content.split('\n')
                formatted_lines = []

                for line in lines:
                    line = line.strip()
                    if line:
                        if not line.startswith('　　'):
                            formatted_lines.append(f'　　{line}')
                        else:
                            formatted_lines.append(line)
                    else:
                        formatted_lines.append('')

                f.write('\n'.join(formatted_lines))
                f.write('\n\n\n')

        safe_print(f"已保存到: {output_path}")
    except Exception as e:
        safe_print(f"保存TXT文件失败: {e}")


def save_as_epub(output_path: str, book_name: str, author: str, description: str,
                 chapter_results: Dict, chapters: List[Dict]):
    """保存为EPUB格式"""
    try:
        from ebooklib import epub
    except ImportError:
        safe_print("错误: 请先安装 ebooklib")
        safe_print("运行: pip install ebooklib")
        return

    try:
        book = epub.EpubBook()
        book.set_identifier(f'book_{book_name}_{int(time.time())}')
        book.set_title(book_name)
        book.set_language('zh-CN')
        book.add_author(author)
        book.add_metadata('DC', 'description', description)

        book.toc = []
        spine = ['nav']

        for idx in sorted(chapter_results.keys()):
            result = chapter_results[idx]
            chapter = epub.EpubHtml(
                title=result['title'],
                file_name=f'chap_{idx}.xhtml',
                lang='zh-CN'
            )

            content = result['content']
            lines = content.split('\n')
            html_paragraphs = []

            for line in lines:
                line = line.strip()
                if line:
                    if not line.startswith('　　'):
                        line = f'　　{line}'
                    html_paragraphs.append(f'<p>{line}</p>')

            html_content = f'<h1>{result["title"]}</h1>\n' + '\n'.join(html_paragraphs)
            chapter.content = html_content.encode('utf-8')

            book.add_item(chapter)
            book.toc.append(chapter)
            spine.append(chapter)

        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = spine

        epub.write_epub(output_path, book, {})
        safe_print(f"已保存到: {output_path}")
    except Exception as e:
        safe_print(f"保存EPUB文件失败: {e}")


def download_novel(book_id: str, save_path: str, file_format: str = 'txt',
                   start_chapter: Optional[int] = None, end_chapter: Optional[int] = None):
    """下载小说主函数"""

    name = None
    author = None
    description = None
    chapters = []
    chapter_results = {}
    downloaded = set()
    output_path = None
    executor = None

    def signal_handler(sig, frame):
        safe_print("\n\n检测到程序中断，正在清理资源...")
        stop_flag.set()  # 设置停止标志

        # 关闭线程池
        if executor:
            safe_print("正在停止下载任务...")
            executor.shutdown(wait=False, cancel_futures=True)
            time.sleep(1)  # 给线程一点时间响应

        # 保存已下载内容
        if chapter_results and output_path and name:
            safe_print("正在保存已下载内容...")
            try:
                if file_format == 'txt':
                    save_as_txt(output_path, name, author, description, chapter_results, chapters)
                else:
                    save_as_epub(output_path, name, author, description, chapter_results, chapters)
            except Exception as e:
                safe_print(f"保存文件时出错: {e}")

        # 保存下载状态
        if downloaded:
            try:
                save_status(save_path, downloaded)
            except Exception as e:
                safe_print(f"保存状态时出错: {e}")

        # 关闭所有驱动
        safe_print("正在关闭浏览器...")
        close_all_drivers()

        safe_print("已保存进度，程序退出")
        os._exit(0)  # 强制退出所有线程

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    stop_flag.clear()  # 重置停止标志

    try:
        safe_print("\n" + "=" * 60)
        safe_print("步骤 1/8: 获取书籍信息")
        safe_print("=" * 60)
        name, author, description = get_book_info(book_id)
        if not name:
            safe_print("✗ 获取书籍信息失败，请检查书籍ID是否正确")
            return

        safe_print("\n" + "=" * 60)
        safe_print("步骤 2/8: 获取章节列表")
        safe_print("=" * 60)
        chapters = get_chapter_list(book_id)
        if not chapters:
            safe_print("✗ 获取章节列表失败")
            return

        safe_print("\n" + "=" * 60)
        safe_print("步骤 3/8: 处理章节范围")
        safe_print("=" * 60)
        if start_chapter is not None and end_chapter is not None:
            chapters = chapters[start_chapter:end_chapter + 1]
            safe_print(f"✓ 已选择章节范围: 第{start_chapter + 1}章 - 第{end_chapter + 1}章 (共{len(chapters)}章)")
        else:
            safe_print(f"✓ 将下载全部章节 (共{len(chapters)}章)")

        safe_print("\n" + "=" * 60)
        safe_print("步骤 4/8: 加载下载状态")
        safe_print("=" * 60)
        os.makedirs(save_path, exist_ok=True)
        downloaded = load_status(save_path)
        safe_print(f"✓ 已下载章节数: {len(downloaded)}")

        if downloaded and start_chapter is None:
            safe_print(f"⚠ 检测到之前下载过《{name}》")
            # 在 CI 环境自动继续
            if not os.environ.get('CI'):
                choice = input("是否继续下载? (y/n): ").strip().lower()
                if choice != 'y':
                    safe_print("已取消下载")
                    return
            else:
                safe_print("CI 环境自动继续下载")

        safe_print("\n" + "=" * 60)
        safe_print("步骤 5/8: 筛选待下载章节")
        safe_print("=" * 60)
        todo_chapters = [ch for ch in chapters if ch['id'] not in downloaded]
        if not todo_chapters:
            safe_print("✓ 所有章节已下载完成")
            return

        safe_print(f"✓ 待下载章节数: {len(todo_chapters)}")
        safe_print(f"✓ 书名: 《{name}》")
        safe_print(f"✓ 作者: {author}")

        safe_print("\n" + "=" * 60)
        safe_print("步骤 6/8: 准备输出文件")
        safe_print("=" * 60)
        output_filename = f"{name}.{file_format}"
        output_path = os.path.join(save_path, output_filename)
        safe_print(f"✓ 输出文件: {output_path}")

        safe_print("\n" + "=" * 60)
        safe_print("步骤 7/8: 开始下载章节")
        safe_print(f"使用 {CONFIG['max_workers']} 个线程")
        safe_print("=" * 60)
        chapter_results = {}
        lock = threading.Lock()

        executor = ThreadPoolExecutor(max_workers=CONFIG["max_workers"])
        try:
            futures = {executor.submit(get_chapter_content, ch): ch for ch in todo_chapters}

            with tqdm(total=len(todo_chapters), desc="下载进度") as pbar:
                for future in as_completed(futures):
                    if stop_flag.is_set():  # 检查停止标志
                        break

                    chapter = futures[future]
                    try:
                        content = future.result(timeout=30)  # 添加超时
                        if content:
                            processed_content = process_chapter_content(content)
                            with lock:
                                chapter_results[chapter['index']] = {
                                    'title': chapter['title'],
                                    'content': processed_content
                                }
                                downloaded.add(chapter['id'])

                            if len(chapter_results) % 10 == 0:
                                save_status(save_path, downloaded)
                        else:
                            safe_print(f"章节 {chapter['title']} 下载失败")
                    except Exception as e:
                        safe_print(f"处理章节 {chapter['title']} 时出错: {e}")
                    finally:
                        pbar.update(1)
        finally:
            executor.shutdown(wait=True)  # 确保线程池关闭

        safe_print("\n" + "=" * 60)
        safe_print("步骤 8/8: 保存文件")
        safe_print("=" * 60)
        if chapter_results:
            if file_format == 'txt':
                save_as_txt(output_path, name, author, description, chapter_results, chapters)
            else:
                save_as_epub(output_path, name, author, description, chapter_results, chapters)

            save_status(save_path, downloaded)
            safe_print("\n" + "=" * 60)
            safe_print(f"✓ 下载完成！成功下载 {len(chapter_results)} 章")
            safe_print("=" * 60)
        else:
            safe_print("\n" + "=" * 60)
            safe_print("✗ 没有成功下载任何章节")
            safe_print("=" * 60)

    except Exception as e:
        safe_print("\n" + "=" * 60)
        safe_print(f"✗ 下载过程中出错: {e}")
        safe_print("=" * 60)
        import traceback
        traceback.print_exc()
    finally:
        safe_print("\n正在清理资源...")
        close_all_drivers()
        safe_print("✓ 资源清理完成")


def get_chapter_range(total_chapters: int) -> Tuple[Optional[int], Optional[int]]:
    """获取章节范围"""
    print(f"\n总章节数: {total_chapters}")

    while True:
        try:
            start = input("请输入起始章节序号 (从1开始，留空表示从第1章开始): ").strip()
            if not start:
                start_idx = 0
            else:
                start_idx = int(start) - 1

            end = input("请输入结束章节序号 (留空表示到最后一章): ").strip()
            if not end:
                end_idx = total_chapters - 1
            else:
                end_idx = int(end) - 1

            if start_idx < 0 or end_idx >= total_chapters or start_idx > end_idx:
                print(f"无效的范围，请确保起始章节在1-{total_chapters}之间，且起始章节不大于结束章节")
                continue

            return start_idx, end_idx
        except ValueError:
            print("请输入有效的数字")
        except KeyboardInterrupt:
            return None, None


def main():
    """主函数"""
    # 检测运行环境
    is_ci = os.environ.get('CI')
    if is_ci:
        print("=" * 60, flush=True)
        print("检测到 GitHub Actions 环境", flush=True)
        print(f"Python 版本: {sys.version}", flush=True)
        print(f"工作目录: {os.getcwd()}", flush=True)
        print("=" * 60, flush=True)

    print("""
╔═══════════════════════════════════════════════╗
║          书吧小说下载器 v1.3                    ║
╚═══════════════════════════════════════════════╝

使用说明:
1. 书籍ID从小说页面URL获取
2. 支持断点续传，下载状态保存在 download_status.json
3. 默认线程数为1，避免触发反爬虫机制
4. 支持指定章节范围下载
5. 支持txt和epub两种格式

环境要求:
- Chrome浏览器
- ChromeDriver (需要与Chrome版本匹配)

按 Ctrl+C 可随时中断下载，程序会立即停止并保存已下载内容
""", flush=True)

    workers_input = input(f"请输入下载线程数 (默认1，推荐1-3): ").strip()
    if workers_input.isdigit() and int(workers_input) > 0:
        CONFIG["max_workers"] = int(workers_input)
        print(f"已设置线程数为: {CONFIG['max_workers']}")

    while True:
        try:
            book_id = input("\n请输入书籍ID (输入q退出): ").strip()
            if book_id.lower() == 'q':
                print("感谢使用，再见!")
                break

            if not book_id:
                print("书籍ID不能为空")
                continue

            save_path = input("保存路径 (留空为当前目录): ").strip() or os.getcwd()

            print("\n请选择操作:")
            print("1. 下载全部章节 (txt格式)")
            print("2. 下载全部章节 (epub格式)")
            print("3. 指定章节范围下载")

            choice = input("请输入选项 (1/2/3): ").strip()

            start_chapter = None
            end_chapter = None
            file_format = 'txt'

            if choice == '1':
                file_format = 'txt'
            elif choice == '2':
                file_format = 'epub'
            elif choice == '3':
                temp_name, _, _ = get_book_info(book_id)
                if temp_name:
                    temp_chapters = get_chapter_list(book_id)
                    if temp_chapters:
                        start_chapter, end_chapter = get_chapter_range(len(temp_chapters))
                        if start_chapter is None:
                            print("取消指定章节范围")
                            continue

                        fmt = input("请选择格式 (1:txt, 2:epub): ").strip()
                        file_format = 'epub' if fmt == '2' else 'txt'
                    else:
                        print("无法获取章节列表")
                        continue
                else:
                    print("无法获取书籍信息")
                    continue
            else:
                print("无效的选择，使用默认txt格式")

            download_novel(book_id, save_path, file_format, start_chapter, end_chapter)

            print("\n" + "=" * 50 + "\n")

        except KeyboardInterrupt:
            print("\n\n程序已退出")
            close_all_drivers()
            break
        except SystemExit:
            close_all_drivers()
            break
        except Exception as e:
            print(f"错误: {e}")
            import traceback
            traceback.print_exc()

    # 主循环结束后清理资源
    close_all_drivers()


if __name__ == "__main__":
    main()
