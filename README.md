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
pdm run python main.py <input_directory> <output_directory> [options]
```

## Usage

```bash
python main.py <input_directory> <output_directory> [options]
```

### Options

- `-t/--threshold`: Similarity threshold (Hamming distance, default 10)
- `-s/--hash-size`: Hash size (default 8)
- `-p/--preview`: Enable similar image preview

## Examples

```bash
# Basic usage
python main.py ~/Pictures/input ~/Pictures/unique

# Stricter similarity comparison (threshold 5)
python main.py ~/Pictures/input ~/Pictures/unique -t 5

# Enable preview mode
python main.py ~/Pictures/input ~/Pictures/unique -p
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
