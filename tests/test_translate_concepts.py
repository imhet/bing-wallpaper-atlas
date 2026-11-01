from crawler.translate_concepts import sanitize


def test_sanitize_strips_cjk_echo_and_leftover_separators():
    # 模型偶尔把原中文词回显进同义词列表
    assert sanitize("dried wood,枯树, dead wood") == "dried wood, dead wood"
    assert sanitize("fence, fence panel,栅栏板") == "fence, fence panel"
    assert sanitize("aurora borealis, northern lights, 极光") == "aurora borealis, northern lights"


def test_sanitize_keeps_pure_english_untouched():
    assert sanitize("snowy mountain, snow-capped peak") == "snowy mountain, snow-capped peak"


def test_sanitize_pure_chinese_becomes_empty_for_retry():
    # 整条没翻出来的：清空后由续跑逻辑重翻
    assert sanitize("穴鸮") == ""
