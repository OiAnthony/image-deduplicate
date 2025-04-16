# Image Deduplication Tool

A tool for finding and removing similar/duplicate images using perceptual hashing algorithm.

## Features

- Supports multiple image formats: JPG/JPEG/PNG/BMP/GIF/TIFF
- Uses average hash (aHash) algorithm to calculate image fingerprints
- Caches hash values to speed up duplicate processing
- Adjustable similarity threshold (Hamming distance)
- Option to copy unique images to output directory
- Supports previewing similar image groups

## Installation

```bash
# Install PDM if you haven't already
pip install --user pdm

# Install project dependencies
pdm install
```

## Development Setup

```bash
# Install development dependencies
pdm install --dev

# Run the script
pdm run python src/image_deduplicate/core.py <input_directory> <output_directory> [options]
```

## Usage

```bash
python main.py <input_directory> <output_directory> [options]
```

### Options

- `-t/--threshold`：哈希距离阈值（Hamming distance，默认 10，数值越小越严格）
- `-s/--hash-size`：哈希尺寸（默认 8，数值越大越精确但速度较慢）
- `-p/--preview`：启用相似图片分组预览（需要图形界面支持）

## Examples

```bash
# 基本用法
python src/image_deduplicate/core.py ~/Pictures/input ~/Pictures/unique

# 更严格的相似度比较（阈值 5）
python src/image_deduplicate/core.py ~/Pictures/input ~/Pictures/unique -t 5

# 启用预览模式
python src/image_deduplicate/core.py ~/Pictures/input ~/Pictures/unique -p
```

## How It Works

1. Traverse all image files in the input directory
2. Calculate perceptual hash for each image (using cache for speed)
3. Group similar images based on Hamming distance
4. Select representative images from each group to copy to output directory

## Notes

- Output directory will be created automatically
- Hash cache is stored in `.image_hash_cache.db` file
- Preview feature requires GUI support
