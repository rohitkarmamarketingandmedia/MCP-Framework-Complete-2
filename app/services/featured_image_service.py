"""
MCP Framework - Featured Image Service
Creates professional featured images with text overlays for blog posts
Like Nandip's style - client photos with SEO titles overlaid
"""
import os
import io
import uuid
import logging
import requests
from typing import Optional, Dict, List, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Try to import PIL
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    logger.warning("PIL/Pillow not installed. Install with: pip install Pillow")


class FeaturedImageConfig:
    """Configuration for featured image generation"""
    
    # Output directory
    OUTPUT_DIR = os.getenv('FEATURED_IMAGE_DIR', 'static/uploads/featured')
    OUTPUT_URL = os.getenv('FEATURED_IMAGE_URL', '/static/uploads/featured')
    
    # Default dimensions (WordPress featured image)
    DEFAULT_WIDTH = 1200
    DEFAULT_HEIGHT = 630  # Facebook/LinkedIn optimal
    
    # Font settings
    FONT_DIR = os.getenv('FONT_DIR', 'static/fonts')
    DEFAULT_FONT = 'Montserrat-Bold.ttf'
    FALLBACK_FONT = 'DejaVuSans-Bold.ttf'
    
    # Templates
    TEMPLATES = {
        'gradient_bottom': {
            'name': 'Gradient Bottom',
            'description': 'Dark gradient at bottom with white text',
            'text_position': 'bottom',
            'text_color': (255, 255, 255),
            'gradient_colors': [(0, 0, 0, 0), (0, 0, 0, 200)],
            'gradient_height': 0.5
        },
        'gradient_full': {
            'name': 'Full Overlay',
            'description': 'Dark overlay on entire image',
            'text_position': 'center',
            'text_color': (255, 255, 255),
            'overlay_color': (0, 0, 0, 120)
        },
        'banner_bottom': {
            'name': 'Solid Banner',
            'description': 'Solid color banner at bottom',
            'text_position': 'bottom_banner',
            'text_color': (255, 255, 255),
            'banner_color': (30, 64, 175),  # Blue
            'banner_height': 120
        },
        'banner_branded': {
            'name': 'Branded Banner',
            'description': 'Uses client brand color',
            'text_position': 'bottom_banner',
            'text_color': (255, 255, 255),
            'use_brand_color': True,
            'banner_height': 120
        },
        'banner_left': {
            'name': 'Professional Left Banner',
            'description': 'Large text on colored left banner - like professional featured images',
            'text_position': 'left_banner',
            'text_color': (255, 255, 255),
            'banner_color': (30, 64, 175),  # Blue - can be overridden by brand color
            'use_brand_color': True,
            'banner_width': 0.45  # 45% of image width
        },
        'split_left': {
            'name': 'Split Left',
            'description': 'Text on left side with gradient',
            'text_position': 'left',
            'text_color': (255, 255, 255),
            'gradient_width': 0.5
        },
        'minimal': {
            'name': 'Minimal',
            'description': 'Light text shadow, clean look',
            'text_position': 'bottom_left',
            'text_color': (255, 255, 255),
            'shadow_only': True
        }
    }


class FeaturedImageService:
    """Service for creating featured images with text overlays"""
    
    def __init__(self):
        self.config = FeaturedImageConfig()
        self._ensure_directories()
        self._font_cache = {}
    
    def _ensure_directories(self):
        """Create output directories if they don't exist"""
        os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)
        os.makedirs(self.config.FONT_DIR, exist_ok=True)
    
    def is_available(self) -> bool:
        """Check if PIL is available"""
        return PIL_AVAILABLE
    
    def get_templates(self) -> Dict:
        """Get available templates"""
        return self.config.TEMPLATES
    
    def _get_font(self, size: int) -> 'ImageFont':
        """Get font, with caching and fallback"""
        cache_key = f"{size}"
        if cache_key in self._font_cache:
            return self._font_cache[cache_key]
        
        font = None
        
        # Try custom font
        font_path = os.path.join(self.config.FONT_DIR, self.config.DEFAULT_FONT)
        if os.path.exists(font_path):
            try:
                font = ImageFont.truetype(font_path, size)
            except Exception as e:
                logger.warning(f"Could not load font {font_path}: {e}")
        
        # Try fallback font
        if not font:
            fallback_path = os.path.join(self.config.FONT_DIR, self.config.FALLBACK_FONT)
            if os.path.exists(fallback_path):
                try:
                    font = ImageFont.truetype(fallback_path, size)
                except Exception:
                    pass
        
        # Try system fonts
        if not font:
            system_fonts = [
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
                '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
                '/System/Library/Fonts/Helvetica.ttc',
                'C:\\Windows\\Fonts\\arial.ttf'
            ]
            for sys_font in system_fonts:
                if os.path.exists(sys_font):
                    try:
                        font = ImageFont.truetype(sys_font, size)
                        break
                    except Exception:
                        continue
        
        # Ultimate fallback - default PIL font
        if not font:
            font = ImageFont.load_default()
        
        self._font_cache[cache_key] = font
        return font
    
    def _load_image(self, source: str) -> Optional['Image.Image']:
        """Load image from URL or file path"""
        if not PIL_AVAILABLE:
            logger.error("PIL not available")
            return None
        
        logger.info(f"Loading image from: {source}")
        
        try:
            if source.startswith('http://') or source.startswith('https://'):
                logger.info(f"Fetching from URL: {source}")
                response = requests.get(source, timeout=30)
                if response.status_code == 200:
                    return Image.open(io.BytesIO(response.content))
                else:
                    logger.error(f"Failed to fetch image: HTTP {response.status_code}")
            elif source.startswith('/static/'):
                # Handle relative static paths - convert to absolute file path
                # Get the root directory (where static folder is)
                root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                absolute_path = os.path.join(root_dir, source.lstrip('/'))
                logger.info(f"Converted relative path to: {absolute_path}")
                if os.path.exists(absolute_path):
                    return Image.open(absolute_path)
                else:
                    logger.error(f"File not found: {absolute_path}")
            else:
                if os.path.exists(source):
                    return Image.open(source)
                else:
                    logger.error(f"File not found: {source}")
        except Exception as e:
            logger.error(f"Failed to load image from {source}: {e}")
            import traceback
            traceback.print_exc()
        
        return None
    
    def _resize_and_crop(self, img: 'Image.Image', width: int, height: int) -> 'Image.Image':
        """Resize and crop image to exact dimensions (cover mode)"""
        # Calculate ratios
        img_ratio = img.width / img.height
        target_ratio = width / height
        
        if img_ratio > target_ratio:
            # Image is wider - crop sides
            new_height = height
            new_width = int(height * img_ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            left = (new_width - width) // 2
            img = img.crop((left, 0, left + width, height))
        else:
            # Image is taller - crop top/bottom
            new_width = width
            new_height = int(width / img_ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            top = (new_height - height) // 2
            img = img.crop((0, top, width, top + height))
        
        return img
    
    def _wrap_text(self, text: str, font: 'ImageFont', max_width: int) -> List[str]:
        """Wrap text to fit within max_width"""
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = font.getbbox(test_line)
            text_width = bbox[2] - bbox[0]
            
            if text_width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines
    
    def _add_gradient_bottom(self, img: 'Image.Image', height_ratio: float = 0.5) -> 'Image.Image':
        """Add gradient overlay at bottom"""
        gradient = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(gradient)
        
        gradient_height = int(img.height * height_ratio)
        start_y = img.height - gradient_height
        
        for y in range(start_y, img.height):
            alpha = int(200 * (y - start_y) / gradient_height)
            draw.line([(0, y), (img.width, y)], fill=(0, 0, 0, alpha))
        
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        return Image.alpha_composite(img, gradient)
    
    def _add_overlay(self, img: 'Image.Image', color: Tuple[int, int, int, int]) -> 'Image.Image':
        """Add solid color overlay"""
        overlay = Image.new('RGBA', img.size, color)
        
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        return Image.alpha_composite(img, overlay)
    
    def _add_banner(self, img: 'Image.Image', height: int, color: Tuple[int, int, int]) -> 'Image.Image':
        """Add solid banner at bottom"""
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        draw = ImageDraw.Draw(img)
        y_start = img.height - height
        draw.rectangle([(0, y_start), (img.width, img.height)], fill=(*color, 255))
        
        return img
    
    def _add_left_banner(self, img: 'Image.Image', width_ratio: float, color: Tuple[int, int, int]) -> 'Image.Image':
        """Add solid banner on left side - professional style"""
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # Create overlay
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        banner_width = int(img.width * width_ratio)
        # Semi-transparent banner
        draw.rectangle([(0, 0), (banner_width, img.height)], fill=(*color, 220))
        
        # Composite
        img = Image.alpha_composite(img, overlay)
        
        return img
    
    def _draw_text_with_shadow(
        self, 
        draw: 'ImageDraw.Draw', 
        text: str, 
        position: Tuple[int, int],
        font: 'ImageFont',
        text_color: Tuple[int, int, int],
        shadow_offset: int = 3
    ):
        """Draw text with drop shadow"""
        x, y = position
        
        # Shadow
        shadow_color = (0, 0, 0, 150)
        draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow_color)
        
        # Main text
        draw.text((x, y), text, font=font, fill=text_color)
    
    def create_featured_image(
        self,
        source_image: str,  # URL or file path
        title: str,
        template: str = 'gradient_bottom',
        subtitle: str = None,
        brand_color: Tuple[int, int, int] = None,
        width: int = None,
        height: int = None,
        output_filename: str = None
    ) -> Dict:
        """
        Create featured image with text overlay
        
        Args:
            source_image: URL or path to source image
            title: Main title text (SEO title)
            template: Template name from TEMPLATES
            subtitle: Optional subtitle (e.g., location or tagline)
            brand_color: RGB tuple for branded templates
            width: Output width (default 1200)
            height: Output height (default 630)
            output_filename: Custom filename (auto-generated if not provided)
        
        Returns:
            Dict with success status, file_path, file_url
        """
        if not PIL_AVAILABLE:
            return {
                'success': False,
                'error': 'PIL/Pillow not installed. Install with: pip install Pillow'
            }
        
        # Set defaults
        width = width or self.config.DEFAULT_WIDTH
        height = height or self.config.DEFAULT_HEIGHT
        template_config = self.config.TEMPLATES.get(template, self.config.TEMPLATES['gradient_bottom'])
        
        try:
            # Load source image
            img = self._load_image(source_image)
            if not img:
                return {
                    'success': False,
                    'error': f'Could not load source image: {source_image}'
                }
            
            # Resize and crop to exact dimensions
            img = self._resize_and_crop(img, width, height)
            
            # Ensure RGBA mode
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # Apply template effects
            text_position = template_config.get('text_position', 'bottom')
            
            if template_config.get('overlay_color'):
                img = self._add_overlay(img, template_config['overlay_color'])
            
            if 'gradient_height' in template_config:
                img = self._add_gradient_bottom(img, template_config['gradient_height'])
            
            if 'banner_height' in template_config:
                banner_color = brand_color if template_config.get('use_brand_color') and brand_color else template_config.get('banner_color', (30, 64, 175))
                img = self._add_banner(img, template_config['banner_height'], banner_color)
            
            # Left banner (professional style)
            if 'banner_width' in template_config:
                banner_color = brand_color if template_config.get('use_brand_color') and brand_color else template_config.get('banner_color', (30, 64, 175))
                img = self._add_left_banner(img, template_config['banner_width'], banner_color)
            
            # Prepare for drawing
            draw = ImageDraw.Draw(img)
            text_color = template_config.get('text_color', (255, 255, 255))
            
            # Calculate text size - MUCH LARGER for professional look
            # Target: text should be easily readable and take up significant space
            max_text_width = int(width * 0.45)  # Left side only, like professional designs
            
            # Larger base font sizes
            title_font_size = 72  # Increased from 64
            if len(title) > 40:
                title_font_size = 64
            if len(title) > 60:
                title_font_size = 56
            if len(title) > 80:
                title_font_size = 48
            
            title_font = self._get_font(title_font_size)
            subtitle_font = self._get_font(36)  # Increased from 28
            
            # Wrap text
            title_lines = self._wrap_text(title, title_font, max_text_width)
            
            # Calculate total text height
            line_height = title_font_size + 15  # More line spacing
            total_text_height = len(title_lines) * line_height
            if subtitle:
                total_text_height += 60  # More space for subtitle
            
            # Position text - more padding
            padding = 50
            
            if text_position == 'bottom' or text_position == 'bottom_banner':
                if 'banner_height' in template_config:
                    y_start = height - template_config['banner_height'] + (template_config['banner_height'] - total_text_height) // 2
                else:
                    y_start = height - total_text_height - padding
                x_start = padding
            elif text_position == 'center':
                y_start = (height - total_text_height) // 2
                x_start = padding
            elif text_position == 'bottom_left':
                y_start = height - total_text_height - padding
                x_start = padding
            elif text_position == 'left':
                y_start = (height - total_text_height) // 2
                x_start = padding
            elif text_position == 'left_banner':
                # Center text vertically in left banner area
                y_start = (height - total_text_height) // 2
                x_start = padding
            else:
                y_start = height - total_text_height - padding
                x_start = padding
            
            # Draw title lines
            current_y = y_start
            for line in title_lines:
                if template_config.get('shadow_only'):
                    self._draw_text_with_shadow(draw, line, (x_start, current_y), title_font, text_color)
                else:
                    draw.text((x_start, current_y), line, font=title_font, fill=text_color)
                current_y += line_height
            
            # Draw subtitle
            if subtitle:
                current_y += 10
                if template_config.get('shadow_only'):
                    self._draw_text_with_shadow(draw, subtitle, (x_start, current_y), subtitle_font, text_color)
                else:
                    draw.text((x_start, current_y), subtitle, font=subtitle_font, fill=(*text_color[:3], 200))
            
            # Generate output filename
            if not output_filename:
                output_filename = f"featured_{uuid.uuid4().hex[:8]}.jpg"
            
            # Save image
            output_path = os.path.join(self.config.OUTPUT_DIR, output_filename)
            
            # Convert to RGB for JPEG
            if img.mode == 'RGBA':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            
            img.save(output_path, 'JPEG', quality=90, optimize=True)
            
            # Build URL
            output_url = f"{self.config.OUTPUT_URL}/{output_filename}"
            
            logger.info(f"Created featured image: {output_path}")
            
            return {
                'success': True,
                'file_path': output_path,
                'file_url': output_url,
                'filename': output_filename,
                'width': width,
                'height': height,
                'template': template
            }
            
        except Exception as e:
            logger.error(f"Failed to create featured image: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e)
            }
    
    def create_from_client_library(
        self,
        client_id: str,
        title: str,
        category: str = None,
        template: str = 'gradient_bottom',
        **kwargs
    ) -> Dict:
        """
        Create featured image using image from client's library
        
        Args:
            client_id: Client ID to get image from
            title: Text to overlay
            category: Image category to select from (hero, work, team, etc.)
            template: Template to use
            **kwargs: Additional args passed to create_featured_image
        """
        from app.models.db_models import DBClientImage
        
        logger.info(f"Creating from client library: client_id={client_id}, category={category}")
        
        # Find an image from client's library
        query = DBClientImage.query.filter_by(client_id=client_id, is_active=True)
        if category:
            query = query.filter_by(category=category)
        
        # Order by least recently used to rotate images
        image = query.order_by(DBClientImage.use_count.asc()).first()
        
        if not image:
            logger.warning(f"No images found for client {client_id}")
            return {
                'success': False,
                'error': f'No images found in client library. Upload images first.'
            }
        
        logger.info(f"Found image: {image.id}, file_url={image.file_url}, file_path={image.file_path}")
        
        # Update usage
        image.use_count += 1
        image.last_used_at = datetime.utcnow()
        
        from app.database import db
        db.session.commit()
        
        # Determine source - prefer local file path if it exists
        source = None
        if image.file_path:
            # Check if path exists directly
            if os.path.exists(image.file_path):
                source = image.file_path
            else:
                # Try relative to app root
                root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                full_path = os.path.join(root_dir, image.file_path.lstrip('/'))
                if os.path.exists(full_path):
                    source = full_path
        
        # Fall back to URL
        if not source and image.file_url:
            if image.file_url.startswith('http'):
                source = image.file_url
            else:
                # It's a relative URL like /static/uploads/...
                source = image.file_url  # _load_image will handle this
        
        if not source:
            logger.error(f"Could not determine source for image {image.id}")
            return {
                'success': False,
                'error': 'Could not locate image file'
            }
        
        logger.info(f"Using source: {source}")
        
        result = self.create_featured_image(
            source_image=source,
            title=title,
            template=template,
            **kwargs
        )
        
        if result.get('success'):
            result['source_image_id'] = image.id
            result['source_image'] = image.to_dict()
        
        return result


# Singleton instance
featured_image_service = FeaturedImageService()
