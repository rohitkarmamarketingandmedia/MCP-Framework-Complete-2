"""
MCP Framework - AI Image Generation Service
Generate images for social media posts using multiple AI providers
"""
import os
import io
import json
import time
import base64
import hashlib
import logging
import requests
from datetime import datetime
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)


class ImageConfig:
    """Image generation configuration"""
    
    # OpenAI DALL-E
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    
    # Stability AI
    STABILITY_API_KEY = os.getenv('STABILITY_API_KEY', '')
    
    # Replicate
    REPLICATE_API_TOKEN = os.getenv('REPLICATE_API_TOKEN', '')
    
    # Unsplash (fallback for stock photos)
    UNSPLASH_ACCESS_KEY = os.getenv('UNSPLASH_ACCESS_KEY', '')
    
    # Image storage
    IMAGE_UPLOAD_DIR = os.getenv('IMAGE_UPLOAD_DIR', 'static/uploads/images')
    IMAGE_BASE_URL = os.getenv('IMAGE_BASE_URL', '/static/uploads/images')
    
    # Default settings
    DEFAULT_SIZE = '1024x1024'
    DEFAULT_QUALITY = 'standard'
    
    @classmethod
    def get_available_providers(cls) -> List[str]:
        """Get list of configured providers"""
        providers = []
        if cls.OPENAI_API_KEY:
            providers.append('dalle')
        if cls.STABILITY_API_KEY:
            providers.append('stability')
        if cls.REPLICATE_API_TOKEN:
            providers.append('replicate')
        if cls.UNSPLASH_ACCESS_KEY:
            providers.append('unsplash')
        return providers


class ImageGenerationService:
    """
    AI Image Generation Service
    
    Supports multiple providers:
    - DALL-E 3 (OpenAI) - Best quality, $0.04-0.12 per image
    - Stability AI - Good quality, competitive pricing
    - Replicate - Access to various models (SDXL, etc.)
    - Unsplash - Free stock photos as fallback
    
    Features:
    - Automatic provider fallback
    - Smart prompt enhancement
    - Image caching
    - Multiple aspect ratios
    - Style presets
    """
    
    def __init__(self):
        self.config = ImageConfig()
        self._ensure_upload_dir()
    
    def _ensure_upload_dir(self):
        """Ensure upload directory exists"""
        upload_dir = self.config.IMAGE_UPLOAD_DIR
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir, exist_ok=True)
    
    # ==========================================
    # MAIN GENERATION METHOD
    # ==========================================
    
    def generate_image(
        self,
        prompt: str,
        style: str = 'photorealistic',
        size: str = '1024x1024',
        provider: str = 'auto',
        negative_prompt: str = None,
        quality: str = 'standard',
        client_id: str = None
    ) -> Dict:
        """
        Generate an image from a text prompt
        
        Args:
            prompt: Text description of the image
            style: Style preset (photorealistic, illustration, etc.)
            size: Image dimensions (1024x1024, 1792x1024, 1024x1792)
            provider: 'dalle', 'stability', 'replicate', 'unsplash', or 'auto'
            negative_prompt: What to avoid in the image
            quality: 'standard' or 'hd' (DALL-E only)
            client_id: Optional client ID for organizing images
        
        Returns:
            Dict with 'success', 'url', 'local_path', 'provider', 'revised_prompt'
        """
        # Enhance prompt based on style
        enhanced_prompt = self._enhance_prompt(prompt, style)
        
        # Select provider
        if provider == 'auto':
            provider = self._select_best_provider()
        
        if not provider:
            return {
                'success': False,
                'error': 'No image generation providers configured'
            }
        
        # Generate with selected provider
        try:
            if provider == 'dalle':
                result = self._generate_dalle(enhanced_prompt, size, quality)
            elif provider == 'stability':
                result = self._generate_stability(enhanced_prompt, size, negative_prompt)
            elif provider == 'replicate':
                result = self._generate_replicate(enhanced_prompt, size, negative_prompt)
            elif provider == 'unsplash':
                result = self._search_unsplash(prompt)
            else:
                return {'success': False, 'error': f'Unknown provider: {provider}'}
            
            if result.get('success') and result.get('image_data'):
                # Save image locally
                filename = self._save_image(
                    result['image_data'],
                    provider,
                    client_id
                )
                result['local_path'] = f"{self.config.IMAGE_UPLOAD_DIR}/{filename}"
                result['url'] = f"{self.config.IMAGE_BASE_URL}/{filename}"
                del result['image_data']  # Remove raw data from response
            
            result['provider'] = provider
            result['original_prompt'] = prompt
            result['enhanced_prompt'] = enhanced_prompt
            
            return result
            
        except Exception as e:
            logger.error(f"Image generation failed with {provider}: {e}")
            
            # Try fallback provider
            fallback = self._get_fallback_provider(provider)
            if fallback:
                logger.info(f"Trying fallback provider: {fallback}")
                return self.generate_image(
                    prompt=prompt,
                    style=style,
                    size=size,
                    provider=fallback,
                    negative_prompt=negative_prompt,
                    quality=quality,
                    client_id=client_id
                )
            
            return {
                'success': False,
                'error': str(e),
                'provider': provider
            }
    
    # ==========================================
    # DALL-E (OpenAI)
    # ==========================================
    
    def _generate_dalle(
        self,
        prompt: str,
        size: str = '1024x1024',
        quality: str = 'standard'
    ) -> Dict:
        """Generate image using OpenAI DALL-E 3"""
        if not self.config.OPENAI_API_KEY:
            raise ValueError("OpenAI API key not configured")
        
        # Validate size for DALL-E 3
        valid_sizes = ['1024x1024', '1792x1024', '1024x1792']
        if size not in valid_sizes:
            size = '1024x1024'
        
        headers = {
            'Authorization': f'Bearer {self.config.OPENAI_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'model': 'dall-e-3',
            'prompt': prompt,
            'n': 1,
            'size': size,
            'quality': quality,
            'response_format': 'b64_json'
        }
        
        response = requests.post(
            'https://api.openai.com/v1/images/generations',
            headers=headers,
            json=payload,
            timeout=120
        )
        
        if response.status_code != 200:
            error_data = response.json()
            raise Exception(f"DALL-E error: {error_data.get('error', {}).get('message', 'Unknown error')}")
        
        data = response.json()
        image_data = data['data'][0]
        
        return {
            'success': True,
            'image_data': base64.b64decode(image_data['b64_json']),
            'revised_prompt': image_data.get('revised_prompt', prompt)
        }
    
    # ==========================================
    # STABILITY AI
    # ==========================================
    
    def _generate_stability(
        self,
        prompt: str,
        size: str = '1024x1024',
        negative_prompt: str = None
    ) -> Dict:
        """Generate image using Stability AI"""
        if not self.config.STABILITY_API_KEY:
            raise ValueError("Stability API key not configured")
        
        # Parse size
        try:
            width, height = map(int, size.split('x'))
        except Exception as e:
            width, height = 1024, 1024
        
        # Stability AI dimensions must be multiples of 64
        width = (width // 64) * 64
        height = (height // 64) * 64
        
        headers = {
            'Authorization': f'Bearer {self.config.STABILITY_API_KEY}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        payload = {
            'text_prompts': [
                {'text': prompt, 'weight': 1}
            ],
            'cfg_scale': 7,
            'height': height,
            'width': width,
            'samples': 1,
            'steps': 30
        }
        
        if negative_prompt:
            payload['text_prompts'].append({
                'text': negative_prompt,
                'weight': -1
            })
        
        response = requests.post(
            'https://api.stability.ai/v1/generation/stable-diffusion-xl-1024-v1-0/text-to-image',
            headers=headers,
            json=payload,
            timeout=120
        )
        
        if response.status_code != 200:
            raise Exception(f"Stability AI error: {response.text}")
        
        data = response.json()
        image_base64 = data['artifacts'][0]['base64']
        
        return {
            'success': True,
            'image_data': base64.b64decode(image_base64),
            'seed': data['artifacts'][0].get('seed')
        }
    
    # ==========================================
    # REPLICATE
    # ==========================================
    
    def _generate_replicate(
        self,
        prompt: str,
        size: str = '1024x1024',
        negative_prompt: str = None
    ) -> Dict:
        """Generate image using Replicate (SDXL)"""
        if not self.config.REPLICATE_API_TOKEN:
            raise ValueError("Replicate API token not configured")
        
        # Parse size
        try:
            width, height = map(int, size.split('x'))
        except Exception as e:
            width, height = 1024, 1024
        
        headers = {
            'Authorization': f'Token {self.config.REPLICATE_API_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        # Use SDXL model
        payload = {
            'version': 'stability-ai/sdxl:39ed52f2a78e934b3ba6e2a89f5b1c712de7dfea535525255b1aa35c5565e08b',
            'input': {
                'prompt': prompt,
                'width': width,
                'height': height,
                'num_outputs': 1,
                'scheduler': 'K_EULER',
                'num_inference_steps': 30,
                'guidance_scale': 7.5,
                'refine': 'expert_ensemble_refiner'
            }
        }
        
        if negative_prompt:
            payload['input']['negative_prompt'] = negative_prompt
        
        # Create prediction
        response = requests.post(
            'https://api.replicate.com/v1/predictions',
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 201:
            raise Exception(f"Replicate error: {response.text}")
        
        prediction = response.json()
        prediction_id = prediction['id']
        
        # Poll for completion
        for _ in range(60):  # Max 2 minutes
            time.sleep(2)
            
            poll_response = requests.get(
                f'https://api.replicate.com/v1/predictions/{prediction_id}',
                headers=headers
            )
            
            poll_data = poll_response.json()
            status = poll_data.get('status')
            
            if status == 'succeeded':
                output = poll_data.get('output', [])
                if output:
                    image_url = output[0]
                    # Download the image
                    img_response = requests.get(image_url)
                    return {
                        'success': True,
                        'image_data': img_response.content,
                        'external_url': image_url
                    }
                raise Exception("No output image URL")
            
            elif status == 'failed':
                raise Exception(f"Replicate failed: {poll_data.get('error')}")
        
        raise Exception("Replicate timeout")
    
    # ==========================================
    # UNSPLASH (Stock Photos Fallback)
    # ==========================================
    
    def _search_unsplash(self, query: str) -> Dict:
        """Search Unsplash for stock photos"""
        if not self.config.UNSPLASH_ACCESS_KEY:
            raise ValueError("Unsplash API key not configured")
        
        headers = {
            'Authorization': f'Client-ID {self.config.UNSPLASH_ACCESS_KEY}'
        }
        
        params = {
            'query': query,
            'per_page': 1,
            'orientation': 'squarish'
        }
        
        response = requests.get(
            'https://api.unsplash.com/search/photos',
            headers=headers,
            params=params,
            timeout=30
        )
        
        if response.status_code != 200:
            raise Exception(f"Unsplash error: {response.text}")
        
        data = response.json()
        results = data.get('results', [])
        
        if not results:
            raise Exception(f"No Unsplash images found for: {query}")
        
        photo = results[0]
        image_url = photo['urls']['regular']
        
        # Download image
        img_response = requests.get(image_url)
        
        return {
            'success': True,
            'image_data': img_response.content,
            'external_url': image_url,
            'attribution': {
                'photographer': photo['user']['name'],
                'photographer_url': photo['user']['links']['html'],
                'unsplash_url': photo['links']['html']
            }
        }
    
    # ==========================================
    # HELPER METHODS
    # ==========================================
    
    def _enhance_prompt(self, prompt: str, style: str) -> str:
        """Enhance prompt based on style preset"""
        style_modifiers = {
            'photorealistic': 'Professional photograph, high resolution, natural lighting, sharp focus, realistic details',
            'illustration': 'Digital illustration, clean lines, vibrant colors, modern style, professional artwork',
            'minimal': 'Minimalist design, clean composition, simple shapes, modern aesthetic, negative space',
            'corporate': 'Professional business image, clean and modern, corporate style, high quality stock photo look',
            'social_media': 'Eye-catching social media post image, vibrant colors, engaging composition, modern design',
            'blog_header': 'Wide blog header image, professional, engaging, relevant visual metaphor',
            'product': 'Professional product photography, clean background, studio lighting, commercial quality',
            'lifestyle': 'Lifestyle photography, authentic moment, natural setting, relatable scene',
            'abstract': 'Abstract digital art, creative composition, artistic interpretation, unique visual',
            'vintage': 'Vintage style, retro aesthetic, warm tones, nostalgic feel, classic look'
        }
        
        modifier = style_modifiers.get(style, style_modifiers['photorealistic'])
        
        # Add quality modifiers
        quality_suffix = "8K resolution, highly detailed, professional quality"
        
        # Combine prompt with style
        enhanced = f"{prompt}. {modifier}. {quality_suffix}"
        
        return enhanced
    
    def _select_best_provider(self) -> Optional[str]:
        """Select best available provider"""
        # Priority order: DALL-E > Stability > Replicate > Unsplash
        providers = self.config.get_available_providers()
        
        if 'dalle' in providers:
            return 'dalle'
        elif 'stability' in providers:
            return 'stability'
        elif 'replicate' in providers:
            return 'replicate'
        elif 'unsplash' in providers:
            return 'unsplash'
        
        return None
    
    def _get_fallback_provider(self, current: str) -> Optional[str]:
        """Get fallback provider if current fails"""
        providers = self.config.get_available_providers()
        fallback_order = ['dalle', 'stability', 'replicate', 'unsplash']
        
        # Find next provider after current
        try:
            current_idx = fallback_order.index(current)
            for provider in fallback_order[current_idx + 1:]:
                if provider in providers:
                    return provider
        except ValueError:
            pass
        
        return None
    
    def _save_image(
        self,
        image_data: bytes,
        provider: str,
        client_id: str = None
    ) -> str:
        """Save image to local storage"""
        # Generate unique filename
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        content_hash = hashlib.md5(image_data[:1000]).hexdigest()[:8]
        
        if client_id:
            filename = f"{client_id}_{timestamp}_{content_hash}.png"
        else:
            filename = f"img_{timestamp}_{content_hash}.png"
        
        filepath = os.path.join(self.config.IMAGE_UPLOAD_DIR, filename)
        
        # Save image
        with open(filepath, 'wb') as f:
            f.write(image_data)
        
        logger.info(f"Saved generated image: {filename}")
        
        return filename
    
    # ==========================================
    # BATCH GENERATION
    # ==========================================
    
    def generate_social_images(
        self,
        topic: str,
        platforms: List[str] = None,
        style: str = 'social_media',
        client_id: str = None
    ) -> Dict[str, Dict]:
        """
        Generate optimized images for multiple social platforms
        
        Args:
            topic: Content topic
            platforms: List of platforms (facebook, instagram, linkedin, etc.)
            style: Style preset
            client_id: Client ID
        
        Returns:
            Dict mapping platform to image result
        """
        if platforms is None:
            platforms = ['facebook', 'instagram', 'linkedin']
        
        # Platform-specific sizes and prompts
        platform_configs = {
            'facebook': {
                'size': '1200x630',
                'prompt_suffix': 'optimized for Facebook sharing, engaging post image'
            },
            'instagram': {
                'size': '1080x1080',
                'prompt_suffix': 'Instagram feed post, square format, visually striking'
            },
            'instagram_story': {
                'size': '1080x1920',
                'prompt_suffix': 'Instagram story, vertical format, immersive'
            },
            'linkedin': {
                'size': '1200x627',
                'prompt_suffix': 'professional LinkedIn post, business appropriate'
            },
            'twitter': {
                'size': '1200x675',
                'prompt_suffix': 'Twitter/X post image, attention grabbing'
            },
            'gbp': {
                'size': '1200x900',
                'prompt_suffix': 'Google Business Profile post, professional and local'
            }
        }
        
        results = {}
        
        for platform in platforms:
            config = platform_configs.get(platform, platform_configs['facebook'])
            
            # Adjust prompt for platform
            platform_prompt = f"{topic}, {config['prompt_suffix']}"
            
            # Use closest supported size
            size = self._get_closest_supported_size(config['size'])
            
            result = self.generate_image(
                prompt=platform_prompt,
                style=style,
                size=size,
                client_id=client_id
            )
            
            results[platform] = result
        
        return results
    
    def _get_closest_supported_size(self, target_size: str) -> str:
        """Map target size to closest supported size"""
        # DALL-E supported sizes
        supported = {
            '1024x1024': (1024, 1024),
            '1792x1024': (1792, 1024),
            '1024x1792': (1024, 1792)
        }
        
        try:
            target_w, target_h = map(int, target_size.split('x'))
            target_ratio = target_w / target_h
        except Exception as e:
            return '1024x1024'
        
        # Find closest aspect ratio
        best_match = '1024x1024'
        best_diff = float('inf')
        
        for size_str, (w, h) in supported.items():
            ratio = w / h
            diff = abs(ratio - target_ratio)
            if diff < best_diff:
                best_diff = diff
                best_match = size_str
        
        return best_match
    
    # ==========================================
    # PROMPT GENERATION
    # ==========================================
    
    def generate_image_prompt(
        self,
        topic: str,
        business_type: str = None,
        location: str = None,
        style: str = 'professional'
    ) -> str:
        """
        Generate an optimized image prompt from a topic
        
        Args:
            topic: Content topic
            business_type: Type of business (e.g., 'HVAC', 'dental')
            location: Business location
            style: Desired style
        
        Returns:
            Optimized prompt string
        """
        # Build contextual prompt
        parts = [topic]
        
        if business_type:
            industry_visuals = {
                'hvac': 'heating and cooling equipment, comfortable home interior',
                'dental': 'modern dental office, professional healthcare setting',
                'legal': 'professional law office, legal documents, courthouse',
                'real_estate': 'beautiful property, modern architecture, inviting home',
                'restaurant': 'delicious food presentation, inviting dining atmosphere',
                'fitness': 'modern gym equipment, active lifestyle, healthy living',
                'salon': 'stylish salon interior, beauty and wellness',
                'automotive': 'professional auto service, modern vehicles',
                'construction': 'construction site, building materials, professional craftsmanship',
                'landscaping': 'beautiful garden, professional lawn care, outdoor living'
            }
            
            visual = industry_visuals.get(business_type.lower(), '')
            if visual:
                parts.append(visual)
        
        if location:
            parts.append(f"set in {location}")
        
        # Add style guidance
        style_guidance = {
            'professional': 'professional photography, business quality, trustworthy appearance',
            'friendly': 'warm and inviting, approachable, human connection',
            'modern': 'contemporary design, clean lines, current trends',
            'traditional': 'classic style, timeless appeal, established presence'
        }
        
        parts.append(style_guidance.get(style, style_guidance['professional']))
        
        return ', '.join(parts)


# Singleton instance
_image_service = None


def get_image_service() -> ImageGenerationService:
    """Get or create image generation service instance"""
    global _image_service
    if _image_service is None:
        _image_service = ImageGenerationService()
    return _image_service
