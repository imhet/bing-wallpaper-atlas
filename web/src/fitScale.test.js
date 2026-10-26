// fitScale：沉浸模式图片缩放策略——cover 优先铺满，裁切超限回退 contain。
// cropRatio = 1 - contain/cover（cover 相对 contain 被裁掉的面积比例），
// ≤ maxCrop 用 cover（小黑边换铺满），否则 contain（构图完整优先）。

import { describe, expect, it } from 'vitest'
import { fitScale } from './fitScale'

describe('fitScale', () => {
  it('equal aspect ratios scale exactly to fill (no crop either way)', () => {
    // 16:9 图进 16:9 视口：cover=contain，等比放大到铺满
    expect(fitScale(1920, 1080, 3840, 2160)).toBe(2)
  })

  it('small crop within threshold fills the viewport (cover)', () => {
    // 2:1 图进 1.6:1 视口：cover=1 裁两侧 20%，正好在阈值内 → 铺满
    expect(fitScale(1000, 500, 800, 500)).toBe(1)
  })

  it('excessive crop falls back to contain (composition preserved)', () => {
    // 超宽全景图进方形视口：cover 要裁 90% 画面 → 退回 contain 完整显示
    expect(fitScale(1000, 100, 100, 100)).toBe(0.1)
  })

  it('contain direction when viewport is wider than image', () => {
    // 竖图进横视口：cover 由高决定放大 2 倍裁上下 >20% → contain（宽贴边）
    expect(fitScale(500, 1000, 1000, 1000)).toBe(1)
  })

  it('upscales small images instead of showing them tiny', () => {
    // 640x480 小图进 1920x1080 视口：cover=3（裁上下 25%）>20% → contain=1080/480=2.25，仍大幅放大
    expect(fitScale(640, 480, 1920, 1080)).toBe(2.25)
  })

  it('custom maxCrop loosens the crop budget', () => {
    // 放宽阈值到 30%：640x480 用 cover=3 铺满
    expect(fitScale(640, 480, 1920, 1080, 0.3)).toBe(3)
  })
})
