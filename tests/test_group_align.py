"""group_align：存量记录补 imageKey（图组显式化）+ 同图组 geo tags 并集对齐。

背景：imageKey 只覆盖 build_record 之后的新记录，老记录打标按 id 独立成组——
VLM 生成式输出措辞随机，同图跨市场打出「黄色民居外墙/黄墙建筑/黄色房屋」。
回填后打标按图组收敛（同图只推理一次），geo 地名标签按组并集提升跨语言召回。
"""

from crawler.group_align import (
    backfill_image_keys,
    backfill_mirror_image_keys,
    mirror_slug,
    parse_bing_url_image_key,
)


def test_backfill_fills_null_image_key_from_urlbase(make_record):
    rec = make_record(id="zh-cn-2023-10-05", imageKey=None)
    out = backfill_image_keys([rec])
    assert out[0]["imageKey"] == "ZhangjiajieMist"


def test_backfill_keeps_existing_image_key(make_record):
    rec = make_record(imageKey="ExplicitKey")
    assert backfill_image_keys([rec])[0]["imageKey"] == "ExplicitKey"


def test_backfill_mirror_absolute_stays_null(make_record):
    # npanuhin 镜像 urlbase 无 OHR ID：保持 null，打标按 id 独立组（深史单市场无重复）
    rec = make_record(urlbase="https://bing.npanuhin.me/US/en/2011-06-01.jpg", imageKey=None)
    assert backfill_image_keys([rec])[0]["imageKey"] is None


def test_parse_bing_url_image_key():
    # npanuhin bing_url 带 _UHD.jpg 尾巴，市场后缀不在行尾——正则须放宽
    assert parse_bing_url_image_key("https://bing.com/th?id=OHR.Santenay_DE-DE7807006506_UHD.jpg") == "Santenay"
    assert parse_bing_url_image_key("https://bing.com/th?id=OHR.Fuji_ZH-CN123") == "Fuji"
    assert parse_bing_url_image_key("https://bing.com/images?foo=bar") is None
    assert parse_bing_url_image_key(None) is None


def test_mirror_slug_from_urlbase():
    assert mirror_slug("https://bing.npanuhin.me/DE/de/2024-06-01.jpg") == "DE-de"
    assert mirror_slug("https://bing.npanuhin.me/US/en/2011-06-01.jpg") == "US-en"
    assert mirror_slug("/th?id=OHR.Fuji_ZH-CN1") is None


def test_backfill_mirror_from_bing_mapping(make_record):
    # 镜像记录借 npanuhin JSON 的 bing_url 桥接回 OHR 图组键（同图跨源终于可合并）
    rec = make_record(
        id="de-de-2024-06-01", market="de-de", date="2024-06-01",
        urlbase="https://bing.npanuhin.me/DE/de/2024-06-01.jpg", imageKey=None,
    )
    out = backfill_mirror_image_keys([rec], {("DE-de", "2024-06-01"): "PrideMonthSF"})
    assert out[0]["imageKey"] == "PrideMonthSF"


def test_backfill_mirror_missing_mapping_stays_null(make_record):
    rec = make_record(
        id="fr-fr-2024-06-01", market="fr-fr",
        urlbase="https://bing.npanuhin.me/FR/fr/2024-06-01.jpg", imageKey=None,
    )
    out = backfill_mirror_image_keys([rec], {("DE-de", "2024-06-01"): "PrideMonthSF"})
    assert out[0]["imageKey"] is None


def test_backfill_mirror_bing_relative_untouched(make_record):
    rec = make_record(urlbase="/th?id=OHR.Fuji_ZH-CN1", imageKey=None)
    out = backfill_mirror_image_keys([rec], {("ZH-cn", "2023-10-05"): "Fuji"})
    assert out[0]["imageKey"] is None  # Bing 相对路径归 backfill_image_keys 管，这里不动
