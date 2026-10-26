// 沉浸模式图片缩放：cover 优先铺满屏幕（小图不再缩在黑框中间），
// 但 cover 要裁掉的面积超过 maxCrop 时退回 contain——构图完整比铺满重要。
// 返回值是图片显示尺寸相对原始尺寸的等比缩放系数。
export function fitScale(iw, ih, vw, vh, maxCrop = 0.2) {
  const cover = Math.max(vw / iw, vh / ih)
  const contain = Math.min(vw / iw, vh / ih)
  return 1 - contain / cover > maxCrop ? contain : cover
}
