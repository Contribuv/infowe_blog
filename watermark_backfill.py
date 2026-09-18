# -*- coding: utf-8 -*-
"""历史文章图片批量加水印（手动可选入口；后台保存水印配置后已自动刷新，一般无需运行）。

用法:
  python watermark_backfill.py [域名]          # 只处理未加过水印的图
  python watermark_backfill.py [域名] --force  # 全部重做(从 .originals 无痕原图重新叠当前水印配置)

核心逻辑与后台“保存水印设置自动刷新”共用 app._wm_redo_all，行为完全一致：
遍历 uploads/ 下已上传的位图(avatar/projects/隐藏目录除外)：
  - 默认: 已处理(对应 .originals 存在)跳过; 首次处理先备份无痕原图,再叠水印写回
  - --force: 所有图都从 .originals 读无痕原图重新叠水印
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import UPLOAD_DIR, app  # noqa: E402
from app import _wm_redo_all  # noqa: E402


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    force = '--force' in sys.argv[1:]
    domain = args[0] if args else ''
    name = (app.config.get('blog_name') or '').strip()
    # 文本: 后台自定义 watermark_text 优先；否则「站点名 · 域名」；位置/开关同样读后台配置
    text = (app.config.get('watermark_text') or '').strip() or (name + ' · ' + domain).strip(' ·')
    position = (app.config.get('watermark_position') or '').strip()
    position = position if position in ('br', 'bl', 'tr', 'tl', 'bc') else 'br'
    if (app.config.get('watermark_enabled', '1') or '1') not in ('1', 'on', 'true', 'yes'):
        print('后台已关闭水印，跳过处理')
        return
    if not text:
        print('水印文字为空：请检查后台水印文本配置')
        return
    print('水印文字:', text, '| 位置:', position)

    count, skipped, errs = _wm_redo_all(text, position, force=force)
    print('完成：新增水印 %d，已处理跳过 %d，失败 %d' % (count, skipped, errs))


if __name__ == '__main__':
    main()