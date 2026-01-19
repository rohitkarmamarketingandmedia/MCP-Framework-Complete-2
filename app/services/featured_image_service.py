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
        'branded_right': {
            'name': 'Pro Branded (Right)',
            'description': 'Professional style - blue box on right with title, CTA, and logo',
            'text_position': 'right_box',
            'text_color': (255, 255, 255),
            'box_color': (0, 102, 178),  # Professional blue
            'use_brand_color': True,
            'include_cta': True,
            'include_logo': True
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
            return None
        
        logger.info(f"_load_image: Attempting to load from: {source}")
        
        try:
            if source.startswith('http://') or source.startswith('https://'):
                logger.info(f"_load_image: Fetching from URL...")
                # Add headers to mimic browser request
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'image/*,*/*'
                }
                response = requests.get(source, timeout=30, headers=headers, verify=True)
                logger.info(f"_load_image: Response status: {response.status_code}, content-type: {response.headers.get('content-type', 'unknown')}")
                
                if response.status_code == 200:
                    img = Image.open(io.BytesIO(response.content))
                    logger.info(f"_load_image: Successfully loaded image {img.size}")
                    return img
                else:
                    logger.error(f"_load_image: HTTP error {response.status_code} for {source}")
            else:
                logger.info(f"_load_image: Loading from file path...")
                if os.path.exists(source):
                    img = Image.open(source)
                    logger.info(f"_load_image: Successfully loaded image {img.size}")
                    return img
                else:
                    logger.error(f"_load_image: File not found: {source}")
        except requests.exceptions.SSLError as e:
            logger.error(f"_load_image: SSL error loading {source}: {e}")
            # Try without SSL verification as fallback
            try:
                logger.info(f"_load_image: Retrying without SSL verification...")
                response = requests.get(source, timeout=30, headers=headers, verify=False)
                if response.status_code == 200:
                    img = Image.open(io.BytesIO(response.content))
                    logger.info(f"_load_image: Successfully loaded image (no SSL verify) {img.size}")
                    return img
            except Exception as e2:
                logger.error(f"_load_image: Retry failed: {e2}")
        except requests.exceptions.RequestException as e:
            logger.error(f"_load_image: Request error loading {source}: {e}")
        except Exception as e:
            logger.error(f"_load_image: Failed to load image from {source}: {e}")
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
    
    def _to_title_case(self, text: str) -> str:
        """Convert text to proper Title Case, preserving certain words lowercase"""
        # Words that should stay lowercase (unless first word)
        lowercase_words = {'a', 'an', 'the', 'and', 'but', 'or', 'for', 'nor', 
                          'on', 'at', 'to', 'from', 'by', 'in', 'of', 'with'}
        
        words = text.split()
        result = []
        
        for i, word in enumerate(words):
            # Check if word has special characters
            if word.upper() == word and len(word) <= 4:
                # Keep acronyms as-is (AC, HVAC, etc.)
                result.append(word)
            elif i == 0 or word.lower() not in lowercase_words:
                # Capitalize first word and important words
                result.append(word.capitalize())
            else:
                # Keep prepositions lowercase
                result.append(word.lower())
        
        return ' '.join(result)
    
    def _draw_branded_right_box(self, img: 'Image.Image', title: str, 
                                 brand_color: Tuple[int, int, int],
                                 phone: str = None, cta_text: str = None,
                                 logo_url: str = None) -> 'Image.Image':
        """
        Draw professional branded box on right side of image
        Like Nandip's style - blue box with title, CTA, phone, and logo
        """
        width, height = img.size
        
        # Box dimensions - right 50% of image for more space
        box_width = int(width * 0.50)
        box_x = width - box_width
        box_padding = 50
        
        # Create overlay for the box
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Draw the colored box (semi-transparent)
        box_color_with_alpha = (*brand_color, 220)  # 86% opacity
        draw.rectangle(
            [(box_x, 0), (width, height)],
            fill=box_color_with_alpha
        )
        
        # Composite overlay onto image
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        img = Image.alpha_composite(img, overlay)
        
        # Now draw text on the composited image
        draw = ImageDraw.Draw(img)
        
        # Title - HUGE fonts to match Nandip's reference exactly
        # For 1200x630 image, title needs to be ~140pt to fill the space
        title_font_size = 140  # Massive base size
        if len(title) > 35:
            title_font_size = 120
        if len(title) > 50:
            title_font_size = 100
        if len(title) > 70:
            title_font_size = 85
            
        title_font = self._get_font(title_font_size)
        max_title_width = box_width - (box_padding * 2)
        
        # Wrap title
        title_lines = self._wrap_text(title, title_font, max_title_width)
        
        # Calculate vertical positioning
        title_line_height = int(title_font_size * 1.15)
        title_total_height = len(title_lines) * title_line_height
        
        # Start title from top with padding
        current_y = box_padding + 30
        
        # Draw title lines
        for line in title_lines:
            draw.text(
                (box_x + box_padding, current_y),
                line,
                font=title_font,
                fill=(255, 255, 255)
            )
            current_y += title_line_height
        
        # Add CTA text and phone at BOTTOM of box
        if cta_text or phone:
            # Position CTA and phone at bottom - HUGE fonts like reference
            cta_font_size = 52  # Bigger CTA
            phone_font_size = 90  # Massive phone number
            
            cta_font = self._get_font(cta_font_size)
            phone_font = self._get_font(phone_font_size)
            
            # Calculate bottom positioning
            bottom_section_height = cta_font_size + phone_font_size + 60
            cta_y = height - bottom_section_height - box_padding
            
            cta_display = cta_text or "Call to schedule an appointment"
            draw.text(
                (box_x + box_padding, cta_y),
                cta_display,
                font=cta_font,
                fill=(255, 255, 255)
            )
            
            # Phone number - large and prominent
            if phone:
                phone_y = cta_y + cta_font_size + 20
                draw.text(
                    (box_x + box_padding, phone_y),
                    phone,
                    font=phone_font,
                    fill=(255, 255, 255)
                )
        
        # Add logo in MIDDLE section (between title and CTA) if provided
        if logo_url:
            try:
                logo_img = self._load_image(logo_url)
                if logo_img:
                    # Resize logo to fit - larger size
                    logo_max_width = int((box_width - (box_padding * 2)) * 0.8)
                    logo_max_height = 100
                    logo_ratio = logo_img.width / logo_img.height
                    
                    if logo_img.width > logo_max_width:
                        new_width = logo_max_width
                        new_height = int(new_width / logo_ratio)
                    else:
                        new_width = logo_img.width
                        new_height = logo_img.height
                    
                    if new_height > logo_max_height:
                        new_height = logo_max_height
                        new_width = int(new_height * logo_ratio)
                    
                    logo_img = logo_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    # Position logo in middle section (after title, before CTA)
                    logo_y = current_y + 40  # Below title area
                    logo_x = box_x + box_padding
                    
                    # Paste logo (handle transparency)
                    if logo_img.mode == 'RGBA':
                        img.paste(logo_img, (logo_x, logo_y), logo_img)
                    else:
                        img.paste(logo_img, (logo_x, logo_y))
            except Exception as e:
                logger.warning(f"Could not add logo: {e}")
        
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
        source_image: str = None,  # URL or file path
        title: str = None,
        template: str = 'gradient_bottom',
        subtitle: str = None,
        brand_color: Tuple[int, int, int] = None,
        width: int = None,
        height: int = None,
        output_filename: str = None,
        phone: str = None,
        cta_text: str = None,
        logo_url: str = None,
        source_image_data: bytes = None  # Raw image bytes (alternative to source_image)
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
            phone: Phone number for CTA
            cta_text: Call to action text (default: "Call to schedule an appointment")
            logo_url: URL to client logo image
            source_image_data: Raw image bytes (used instead of source_image if provided)
            logo_url: URL to client logo image
        
        Returns:
            Dict with success status, file_path, file_url
        """
        if not PIL_AVAILABLE:
            return {
                'success': False,
                'error': 'PIL/Pillow not installed. Install with: pip install Pillow'
            }
        
        # Convert title to proper Title Case
        title = self._to_title_case(title)
        
        # Set defaults
        width = width or self.config.DEFAULT_WIDTH
        height = height or self.config.DEFAULT_HEIGHT
        template_config = self.config.TEMPLATES.get(template, self.config.TEMPLATES['gradient_bottom'])
        
        try:
            # Load source image - from bytes or from URL/path
            img = None
            if source_image_data:
                # Load from raw bytes
                logger.info(f"Loading image from {len(source_image_data)} bytes of data")
                try:
                    img = Image.open(io.BytesIO(source_image_data))
                    logger.info(f"Successfully loaded image from bytes: {img.size}")
                except Exception as e:
                    logger.error(f"Failed to load image from bytes: {e}")
            
            if not img and source_image:
                # Load from URL or path
                img = self._load_image(source_image)
            
            if not img:
                return {
                    'success': False,
                    'error': f'Could not load source image: {source_image or "from bytes"}'
                }
            
            # Resize and crop to exact dimensions
            img = self._resize_and_crop(img, width, height)
            
            # Ensure RGBA mode
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            
            # Apply template effects
            text_position = template_config.get('text_position', 'bottom')
            
            # Handle branded_right template separately (full custom rendering)
            if text_position == 'right_box':
                box_color = brand_color if template_config.get('use_brand_color') and brand_color else template_config.get('box_color', (0, 102, 178))
                img = self._draw_branded_right_box(
                    img, title, box_color,
                    phone=phone, cta_text=cta_text, logo_url=logo_url
                )
                # Skip normal text rendering - go straight to save
            else:
                # Normal template processing
                if template_config.get('overlay_color'):
                    img = self._add_overlay(img, template_config['overlay_color'])
                
                if 'gradient_height' in template_config:
                    img = self._add_gradient_bottom(img, template_config['gradient_height'])
                
                if 'banner_height' in template_config:
                    banner_color = brand_color if template_config.get('use_brand_color') and brand_color else template_config.get('banner_color', (30, 64, 175))
                    img = self._add_banner(img, template_config['banner_height'], banner_color)
                
                # Prepare for drawing
                draw = ImageDraw.Draw(img)
                text_color = template_config.get('text_color', (255, 255, 255))
                
                # Calculate text size based on title length
                max_text_width = int(width * 0.85)
                title_font_size = 64
                if len(title) > 50:
                    title_font_size = 48
                if len(title) > 80:
                    title_font_size = 40
                
                title_font = self._get_font(title_font_size)
                subtitle_font = self._get_font(28)
                
                # Wrap text
                title_lines = self._wrap_text(title, title_font, max_text_width)
                
                # Calculate total text height
                line_height = title_font_size + 10
                total_text_height = len(title_lines) * line_height
                if subtitle:
                    total_text_height += 50  # Space for subtitle
                
                # Position text
                padding = 40
                
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
            
            # Ensure output directory exists
            os.makedirs(self.config.OUTPUT_DIR, exist_ok=True)
            
            # Save image locally first
            output_path = os.path.join(self.config.OUTPUT_DIR, output_filename)
            
            # Convert to RGB for JPEG
            if img.mode == 'RGBA':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            
            img.save(output_path, 'JPEG', quality=90, optimize=True)
            
            # Default to local URL
            output_url = f"{self.config.OUTPUT_URL}/{output_filename}"
            
            # Try to upload to FTP if configured
            try:
                from app.services.ftp_storage_service import get_ftp_service
                ftp = get_ftp_service()
                if ftp.is_configured():
                    with open(output_path, 'rb') as f:
                        file_data = f.read()
                    
                    # Extract client_id from source_image path if possible
                    client_id = 'featured'  # Default category
                    if hasattr(self, '_current_client_id'):
                        client_id = self._current_client_id
                    
                    ftp_result = ftp.upload_file(file_data, output_filename, client_id, 'featured')
                    if ftp_result:
                        output_url = ftp_result['file_url']
                        logger.info(f"Featured image uploaded to FTP: {output_url}")
            except Exception as e:
                logger.warning(f"FTP upload for featured image failed, using local: {e}")
            
            logger.info(f"Created featured image: {output_path} -> {output_url}")
            
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
        
        # Find an image from client's library
        query = DBClientImage.query.filter_by(client_id=client_id, is_active=True)
        if category:
            query = query.filter_by(category=category)
        
        # Order by least recently used to rotate images
        image = query.order_by(DBClientImage.use_count.asc()).first()
        
        if not image:
            return {
                'success': False,
                'error': f'No images found in client library. Upload images first.'
            }
        
        # Update usage
        image.use_count += 1
        image.last_used_at = datetime.utcnow()
        
        from app.database import db
        db.session.commit()
        
        # Create featured image - prefer file_path (filesystem) over file_url
        source = None
        source_type = None
        
        # Check filesystem first
        if image.file_path:
            if os.path.exists(image.file_path):
                source = image.file_path
                source_type = 'file_path'
                logger.info(f"Using file_path: {source}")
            else:
                logger.warning(f"file_path does not exist: {image.file_path}")
        
        # Try HTTP URL
        if not source and image.file_url and image.file_url.startswith('http'):
            source = image.file_url
            source_type = 'http_url'
            logger.info(f"Using file_url (http): {source}")
        
        # Try to construct filesystem path from file_url
        if not source and image.file_url and image.file_url.startswith('/static/'):
            # Convert /static/uploads/... to static/uploads/...
            relative_path = image.file_url.lstrip('/')
            if os.path.exists(relative_path):
                source = relative_path
                source_type = 'relative_path'
                logger.info(f"Using file_url as path: {source}")
            else:
                logger.warning(f"Relative path does not exist: {relative_path}")
        
        if not source:
            logger.error(f"Could not locate image. file_path={image.file_path}, file_url={image.file_url}")
            return {
                'success': False,
                'error': 'Image file not found on server. On Render, uploaded files are lost after each deploy. Please upload images to an external service (like Imgur or Cloudinary) and use the URL, or re-upload after each deploy.'
            }
        
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
