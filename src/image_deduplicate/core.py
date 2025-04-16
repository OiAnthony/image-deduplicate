import os
import sys
import argparse
import shutil
import sqlite3
import collections
from concurrent.futures import ProcessPoolExecutor, as_completed
import imagehash
from tqdm import tqdm
from PIL import Image
from PIL import UnidentifiedImageError

# Supported image file extensions
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff"}
# Cache database filename
CACHE_DB_NAME = ".image_hash_cache.db"


def hash_worker(image_path, hash_size):
    """Worker function to calculate image hash."""
    try:
        img_hash = imagehash.phash(Image.open(image_path), hash_size=hash_size)
        return image_path, str(img_hash)
    except FileNotFoundError:
        print(f"Warning: File not found {image_path}", file=sys.stderr)
        return image_path, None
    except UnidentifiedImageError:
        print(f"Warning: Cannot identify image file {image_path}", file=sys.stderr)
        return image_path, None
    except Exception as e:
        print(
            f"Warning: Failed to process {image_path} in worker: {e}", file=sys.stderr
        )
        return image_path, None


def calculate_hash(image_path, hash_size=8):
    """Calculate perceptual hash of an image"""
    try:
        img = Image.open(image_path)
        # Convert to grayscale for better hash stability
        if img.mode != "L":
            img = img.convert("L")
        # Using average_hash, could also consider phash or dhash
        return imagehash.average_hash(img, hash_size=hash_size)
    except Exception as e:
        print(f"\nWarning: Failed to process file {os.path.basename(image_path)}: {e}")
        return None


def find_similar_images(input_dir, hash_size=8, threshold=10):
    """
    Traverse directory, calculate hashes (using cache when available) and find similar images.
    Returns a dict where keys are representative hash values (strings),
    and values are lists of (distance, image_path) tuples sorted by hamming distance.
    """
    hashes = collections.defaultdict(list)
    image_files = []
    db_path = os.path.join(os.path.dirname(__file__) or ".", CACHE_DB_NAME)
    conn = None
    cursor = None

    try:
        # Initialize database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS image_hashes (
                filepath TEXT PRIMARY KEY,
                mtime REAL NOT NULL,
                hash_size INTEGER NOT NULL,
                hash_value TEXT NOT NULL
            )
        """)
        # Create index for query optimization
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_filepath ON image_hashes (filepath)"
        )
        conn.commit()

        print("Scanning image files...")
        for root, _, files in os.walk(input_dir):
            for file in files:
                if os.path.splitext(file)[1].lower() in SUPPORTED_EXTENSIONS:
                    image_files.append(os.path.join(root, file))

        print(
            f"Found {len(image_files)} image files. Calculating/comparing hashes (multiprocessing)..."
        )

        hash_objects = {}
        processed_count = 0
        cache_hits = 0
        hash_results = []

        def check_cache(image_path):
            """
            查询缓存，如果命中，则返回(image_path, img_hash, img_hash_str, True)，否则返回(image_path, None, None, False)
            """
            try:
                current_mtime = os.path.getmtime(image_path)
            except OSError as e:
                print(
                    f"\nWarning: Failed to get file info {os.path.basename(image_path)}: {e}"
                )
                return (image_path, None, None, False)
            cursor.execute(
                "SELECT mtime, hash_size, hash_value FROM image_hashes WHERE filepath=?",
                (image_path,),
            )
            result = cursor.fetchone()
            if result:
                cached_mtime, cached_hash_size, cached_hash_value = result
                if cached_mtime == current_mtime and cached_hash_size == hash_size:
                    try:
                        img_hash = imagehash.hex_to_hash(cached_hash_value)
                        return (image_path, img_hash, cached_hash_value, True)
                    except Exception:
                        pass
            return (image_path, None, None, False)

        # 先查缓存，未命中的再并行计算
        cache_checked = [check_cache(p) for p in image_files]
        cache_hit_items = [item for item in cache_checked if item[3]]
        cache_miss_items = [item for item in cache_checked if not item[3]]
        cache_hits = len(cache_hit_items)

        # 进程池并行计算未命中缓存的图片哈希
        with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor, tqdm(
            total=len(image_files), desc="Processing images", unit="file"
        ) as pbar:
            # 先处理缓存命中的
            for image_path, img_hash, img_hash_str, _ in cache_hit_items:
                hash_results.append((image_path, img_hash, img_hash_str))
                pbar.update(1)
            # 并行处理未命中
            future_to_path = {
                executor.submit(hash_worker, image_path, hash_size): image_path
                for image_path, _, _, _ in cache_miss_items
            }
            for future in as_completed(future_to_path):
                image_path = future_to_path[future]
                img_hash = None
                try:
                    _, img_hash_str = future.result()
                    if img_hash_str is not None:
                        img_hash = imagehash.hex_to_hash(img_hash_str)
                except Exception as e:
                    print(
                        f"\nWarning: Failed to process {os.path.basename(image_path)} in worker: {e}"
                    )
                if img_hash is not None:
                    hash_results.append((image_path, img_hash, img_hash_str))
                    # 主进程写入缓存
                    try:
                        current_mtime = os.path.getmtime(image_path)
                        cursor.execute(
                            "INSERT OR REPLACE INTO image_hashes VALUES (?, ?, ?, ?)",
                            (image_path, current_mtime, hash_size, img_hash_str),
                        )
                        conn.commit()
                    except Exception as e:
                        print(
                            f"\nWarning: Failed to update cache for {os.path.basename(image_path)}: {e}"
                        )
                pbar.update(1)

        # 后续比对逻辑保持不变
        for image_path, img_hash, img_hash_str in hash_results:
            if img_hash is None:
                continue
            matched = False
            for existing_hash_str in list(hash_objects.keys()):
                existing_hash = hash_objects[existing_hash_str]
                distance = img_hash - existing_hash
                if distance <= threshold:
                    hashes[existing_hash_str].append((distance, image_path))
                    matched = True
                    break
            if not matched:
                hash_objects[img_hash_str] = img_hash
                hashes[img_hash_str].append((0, image_path))
            processed_count += 1

        print(f"Processed {processed_count} files (cache hits: {cache_hits})")
        print(f"Found {len(hashes)} unique hash groups")

    except Exception as e:
        print(f"\nError during processing: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return hashes


def copy_unique_images(hashes, output_dir, preview=False):
    """
    Select representative images from similar groups, sort them by similarity,
    and copy to output directory with sequential naming.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Sort hash groups by first image's name (for consistent ordering)
    sorted_hashes = sorted(hashes.items(), key=lambda x: x[1][0][1])

    counter = 1
    for hash_str, images in sorted_hashes:
        # Sort images in group by distance
        images.sort()

        representative = images[0][1]
        ext = os.path.splitext(representative)[1].lower()
        orig_name = os.path.basename(representative)
        dest_path = os.path.join(output_dir, f"{counter}_{orig_name}")

        try:
            shutil.copy2(representative, dest_path)
            print(f"Copied: {orig_name} -> {os.path.basename(dest_path)}")

            if len(images) > 1 and preview:
                print(f"  Similar images ({len(images)-1}):")
                preview_similar_images([img[1] for img in images])

            counter += 1
        except Exception as e:
            print(f"Error copying {representative}: {e}")


def preview_similar_images(image_paths, max_width=1600):
    """Combine similar images into one large image for preview"""
    padding = 10
    images = []
    total_height = padding
    max_img_width = 0

    print("  Preparing preview...")
    for path in image_paths:
        try:
            img = Image.open(path)
            if img.width > max_img_width:
                max_img_width = img.width
            total_height += img.height + padding
            images.append(img)
        except Exception as e:
            print(f"  Warning: Failed to open {os.path.basename(path)}: {e}")

    if not images:
        return

    total_height -= padding

    combined_image = Image.new(
        "RGBA", (max_img_width, total_height), color=(255, 255, 255, 0)
    )

    current_y = 0
    for img in images:
        paste_x = (max_img_width - img.width) // 2
        if img.mode == "RGBA":
            combined_image.paste(img, (paste_x, current_y), img)
        elif img.mode == "LA" or (img.mode == "P" and "transparency" in img.info):
            try:
                img_rgba = img.convert("RGBA")
                combined_image.paste(img_rgba, (paste_x, current_y), img_rgba)
                img_rgba.close()
            except Exception as convert_err:
                print(
                    f"  Warning: Failed to convert {img.filename} to RGBA: {convert_err}, using RGB"
                )
                img_rgb = img.convert("RGB")
                combined_image.paste(img_rgb, (paste_x, current_y))
                img_rgb.close()
        else:
            img_rgb = img.convert("RGB")
            combined_image.paste(img_rgb, (paste_x, current_y))
            img_rgb.close()

        current_y += img.height + padding

    if combined_image.width > max_width:
        ratio = max_width / combined_image.width
        new_height = int(combined_image.height * ratio)
        print(f"  Preview too wide, resizing to {max_width}x{new_height}")
        try:
            combined_image = combined_image.resize(
                (max_width, new_height), Image.Resampling.LANCZOS
            )
        except Exception as resize_err:
            print(f"  Error resizing preview: {resize_err}")

    try:
        print("  Showing preview window...")
        combined_image.show(
            title="Similar images preview (" + str(len(image_paths)) + ")"
        )
        print(
            "  Preview window opened (may be behind other applications). Processing continues..."
        )
    except Exception as e:
        print(f"  Error showing preview: {e}")
        print(
            "  Make sure you have graphical environment or try without --preview option."
        )
    finally:
        for img in images:
            try:
                img.close()
            except Exception:
                pass
        try:
            combined_image.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(
        description="Find and remove duplicate/similar images in a folder."
    )
    parser.add_argument("input_dir", help="Path to input directory containing images.")
    parser.add_argument(
        "output_dir", help="Path to output directory for unique images."
    )
    parser.add_argument(
        "--threshold",
        "-t",
        type=int,
        default=10,
        help="Hamming distance threshold for similarity. Lower values mean more similar. (Default: 5)",
    )
    parser.add_argument(
        "--hash-size",
        "-s",
        type=int,
        default=8,
        help="Size of perceptual hash. Higher values more precise but slower. (Default: 8)",
    )
    parser.add_argument(
        "--preview",
        "-p",
        action="store_true",
        help="Enable preview of similar image groups.",
    )

    args = parser.parse_args()

    if not os.path.isdir(args.input_dir):
        print(
            f"Error: Input directory '{args.input_dir}' does not exist or is invalid."
        )
        return

    print(f"Input directory: {args.input_dir}")
    print(f"Output directory: {args.output_dir}")
    print(f"Similarity threshold (hamming distance): {args.threshold}")
    print(f"Hash size: {args.hash_size}")
    print(f"Preview mode: {'Enabled' if args.preview else 'Disabled'}")

    similar_groups = find_similar_images(args.input_dir, args.hash_size, args.threshold)
    copy_unique_images(similar_groups, args.output_dir, args.preview)


if __name__ == "__main__":
    main()
