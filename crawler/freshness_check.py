"""数据新鲜度检查：daily 断更红灯。

挂在 link-check.yml 里（每天 UTC 14:00），探线上 aggregations.json 的
latest_date——落后今天（UTC）超过 1 天即 exit 1 红灯，触发 GitHub 失败
邮件告警。容忍 1 天是给 daily 的运行延迟留余量（cron 排队经常晚几小时）。

局限：link-check 自己也走 schedule 触发，若 GitHub schedule 通道整体
死亡则本检查同样不会运行（2026-11-13~15 实测发生过）——那类故障需要
GitHub 之外的心跳兜底，属已知盲区。
"""
import argparse
import datetime
import sys

import requests


def is_stale(latest_date: str, today: datetime.date, max_lag_days: int = 1) -> bool:
    """latest_date 落后 today 超过 max_lag_days 天为过期。"""
    latest = datetime.date.fromisoformat(latest_date)
    return (today - latest).days > max_lag_days


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="https://imhet.github.io/bing-wallpaper-atlas/data/aggregations.json",
        help="线上 aggregations.json 地址",
    )
    parser.add_argument("--max-lag-days", type=int, default=1)
    args = parser.parse_args()

    try:
        resp = requests.get(args.url, timeout=30)
        resp.raise_for_status()
        latest = resp.json().get("latest_date")
    except Exception as exc:
        print(f"::error::aggregations.json 拉取/解析失败：{exc}")
        return 1

    if not latest:
        print("::error::aggregations.json 缺少 latest_date 字段")
        return 1

    today = datetime.datetime.now(datetime.timezone.utc).date()
    if is_stale(latest, today, args.max_lag_days):
        print(
            f"::error::数据断更：线上 latest_date={latest}，"
            f"落后今天({today.isoformat()})超过 {args.max_lag_days} 天——"
            "daily 抓取或部署失败，去 Actions 查最近几次运行"
        )
        return 1

    print(f"数据新鲜：latest_date={latest}（今天 {today.isoformat()}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
