"""
监控脚本：检查渠道可用性，定期输出统计摘要
用法: python scripts/monitor.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.models.base import SessionLocal
from app.models.channel import Channel
from app.services.log_service import get_overview_stats


def check_channels(db):
    channels = db.query(Channel).all()
    print(f"\n{'='*50}")
    print(f"渠道状态检查 ({time.strftime('%Y-%m-%d %H:%M:%S')})")
    print(f"{'='*50}")
    for ch in channels:
        status_icon = "✓" if ch.status == 1 else "✗"
        print(f"  {status_icon} [{ch.channel_type}] {ch.name} — 错误次数: {ch.error_count}")
        if ch.last_error:
            print(f"      最后错误: {ch.last_error[:80]}")


def print_stats(db):
    stats = get_overview_stats(db)
    print(f"\n统计摘要:")
    print(f"  总请求数: {stats['total_requests']}")
    print(f"  今日请求: {stats['today_requests']}")
    print(f"  总消费:   ${stats['total_cost']:.4f}")
    print(f"  今日消费: ${stats['today_cost']:.4f}")


if __name__ == "__main__":
    db = SessionLocal()
    try:
        while True:
            check_channels(db)
            print_stats(db)
            print("\n下次检查在 60 秒后...")
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n监控已停止")
    finally:
        db.close()
