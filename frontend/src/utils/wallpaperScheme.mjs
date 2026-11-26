const linearSrgb = Array.from({ length: 256 }, (_, value) => {
  const channel = value / 255
  return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
})

export async function sampleWallpaper(url) {
  const image = new Image()
  image.src = url
  await image.decode()

  const scale = Math.min(1, 64 / Math.max(image.naturalWidth, image.naturalHeight))
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(image.naturalWidth * scale))
  canvas.height = Math.max(1, Math.round(image.naturalHeight * scale))
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) return 'dark'
  context.drawImage(image, 0, 0, canvas.width, canvas.height)
  const { data } = context.getImageData(0, 0, canvas.width, canvas.height)
  const samples = []
  let totalWeight = 0
  for (let i = 0; i < data.length; i += 4) {
    const weight = data[i + 3]
    if (!weight) continue
    const luminance = 0.2126 * linearSrgb[data[i]] + 0.7152 * linearSrgb[data[i + 1]]
      + 0.0722 * linearSrgb[data[i + 2]]
    const lightness = luminance > 216 / 24389 ? 116 * Math.cbrt(luminance) - 16 : luminance * (24389 / 27)
    totalWeight += weight
    samples.push({ lightness, weight })
  }
  if (!totalWeight) return 'dark'

  samples.sort((a, b) => a.lightness - b.lightness)
  const lower = totalWeight * 0.1
  const upper = totalWeight * 0.9
  let position = 0
  let sum = 0
  for (const sample of samples) {
    const end = position + sample.weight
    const weight = Math.max(0, Math.min(end, upper) - Math.max(position, lower))
    sum += sample.lightness * weight
    position = end
  }
  return sum / (upper - lower) >= 58 ? 'light' : 'dark'
}
