#!/usr/bin/env node
import fs from 'node:fs'
import fsp from 'node:fs/promises'
import path from 'node:path'
import sharp from 'sharp'

const srcDir = path.resolve('content/images/glyphs-app-mcp')
const outDir = path.resolve('public/images/glyphs-app-mcp')
const requiredHero = 'glyphs-mcp.png' // splash referenced by content/glyphs-mcp.md

async function ensureDir(dir) {
  await fsp.mkdir(dir, { recursive: true })
}

async function convertPngToWebp(inputPath, outputPath) {
  await sharp(inputPath)
    .webp({ quality: 82, effort: 5 })
    .toFile(outputPath)
}

async function main() {
  await ensureDir(outDir)

  const entries = await fsp.readdir(srcDir, { withFileTypes: true })
  const pngs = entries.filter((e) => e.isFile() && e.name.toLowerCase().endsWith('.png'))

  if (pngs.length === 0) {
    console.log('No PNG files found in', srcDir)
    return
  }

  let count = 0
  // Ensure hero image for content/glyphs-mcp.md specifically exists and gets converted first
  const hasHero = pngs.some((e) => e.name === requiredHero)
  if (!hasHero) {
    console.warn(`Warning: expected hero image \`${requiredHero}\` not found in ${srcDir}`)
  } else {
    const inPath = path.join(srcDir, requiredHero)
    const outPath = path.join(outDir, requiredHero.replace(/\.png$/i, '.webp'))
    await convertPngToWebp(inPath, outPath)
    count++
    console.log(`Converted: ${requiredHero} -> ${path.basename(outPath)}`)
  }

  // Convert remaining PNGs (excluding hero if already processed)
  for (const entry of pngs) {
    if (entry.name === requiredHero) continue
    const inPath = path.join(srcDir, entry.name)
    const base = entry.name.replace(/\.png$/i, '')
    const outPath = path.join(outDir, `${base}.webp`)

    await convertPngToWebp(inPath, outPath)
    count++
    console.log(`Converted: ${entry.name} -> ${path.basename(outPath)}`)
  }

  console.log(`Done. ${count} images written to ${outDir}`)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
