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
        """
        Enhance prompt based on style preset with quality safeguards
        
        DALL-E 3 specific optimizations:
        - Clear scene descriptions work better than technical camera specs
        - Negative instructions should be minimal (DALL-E handles internally)
        - Specific visual details produce better results
        """
        style_modifiers = {
            'photorealistic': 'Realistic photograph with natural lighting and authentic details, like a professional stock photo',
            'illustration': 'Clean modern digital illustration with vibrant colors, professional graphic design style',
            'minimal': 'Minimalist composition with clean negative space, simple elegant design, modern aesthetic',
            'corporate': 'Professional business photograph, clean and polished, suitable for corporate marketing',
            'social_media': 'Eye-catching vibrant image perfect for social media, bold colors, engaging composition',
            'blog_header': 'Wide cinematic composition suitable for blog header, editorial photography style',
            'product': 'Clean product photography on white background, professional studio lighting',
            'lifestyle': 'Authentic lifestyle photograph capturing a genuine moment, warm natural tones',
            'abstract': 'Creative abstract composition with artistic visual elements, contemporary design',
            'vintage': 'Warm vintage aesthetic with nostalgic film-like tones and classic styling'
        }
        
        modifier = style_modifiers.get(style, style_modifiers['photorealistic'])
        
        # Quality enhancement - simpler is better for DALL-E 3
        quality_suffix = "High quality, sharp details, professional composition"
        
        # DALL-E 3 handles text avoidance better with simple instructions
        safety_suffix = "No text or words in the image"
        
        # Build enhanced prompt - keep it natural and descriptive
        enhanced = f"{prompt}. {modifier}. {quality_suffix}. {safety_suffix}"
        
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
        
        Best practices for DALL-E 3:
        - Be specific and descriptive
        - Describe the scene like you're explaining it to someone
        - Include lighting, mood, and perspective details
        - Avoid overly technical or negative instructions
        """
        prompt_parts = []
        
        # Industry-specific scene descriptions - detailed and visual
        if business_type:
            industry_scenes = {
                'hvac': {
                    'scene': 'A professional HVAC technician in a clean uniform installing a modern air conditioning unit on the side of a beautiful suburban home',
                    'details': 'sunny day, the technician appears competent and friendly, modern equipment visible, well-maintained house with nice landscaping',
                    'mood': 'professional, trustworthy, residential comfort'
                },
                'plumbing': {
                    'scene': 'A skilled plumber using modern tools to repair pipes under a kitchen sink in a clean, well-lit home',
                    'details': 'organized workspace, professional appearance, homeowner visible in background looking relieved',
                    'mood': 'reliable, professional, problem-solving'
                },
                'roofing': {
                    'scene': 'Professional roofing crew installing new architectural shingles on a residential home at golden hour',
                    'details': 'safety equipment visible, beautiful new roof taking shape, suburban neighborhood setting',
                    'mood': 'skilled craftsmanship, home improvement, quality work'
                },
                'electrical': {
                    'scene': 'Licensed electrician in professional attire working on a modern electrical panel in a new home',
                    'details': 'clean workspace, safety equipment, modern wiring, professional tools',
                    'mood': 'precision, safety, expertise'
                },
                'dental': {
                    'scene': 'Modern dental office with a patient comfortably seated in a state-of-the-art chair, friendly dentist in clean scrubs',
                    'details': 'bright natural lighting, contemporary interior design, calming atmosphere, advanced equipment',
                    'mood': 'welcoming, clean, professional healthcare'
                },
                'real_estate': {
                    'scene': 'Stunning modern home exterior photographed at twilight with warm interior lights glowing',
                    'details': 'manicured lawn, beautiful landscaping, welcoming entrance, aspirational living',
                    'mood': 'luxury, dream home, inviting'
                },
                'landscaping': {
                    'scene': 'Beautifully designed backyard oasis with lush green lawn, flowering plants, and elegant hardscaping',
                    'details': 'perfect manicured grass, colorful seasonal flowers, professional patio design, outdoor living space',
                    'mood': 'serene, beautiful outdoor living, professional design'
                },
                'pest_control': {
                    'scene': 'Professional pest control technician in clean uniform inspecting a beautiful home exterior',
                    'details': 'modern equipment, professional appearance, well-maintained home, protective family atmosphere',
                    'mood': 'protection, professionalism, peace of mind'
                },
                'cleaning': {
                    'scene': 'Sparkling clean modern living room with sunlight streaming through crystal-clear windows',
                    'details': 'immaculate surfaces, organized space, fresh and bright atmosphere, premium home interior',
                    'mood': 'pristine, fresh, satisfying cleanliness'
                },
                'painting': {
                    'scene': 'Professional painter carefully applying fresh paint to a home interior, transforming the space',
                    'details': 'clean workspace with drop cloths, high-quality paint and tools, dramatic before-after potential',
                    'mood': 'transformation, craftsmanship, home improvement'
                },
                'windows': {
                    'scene': 'Beautiful new energy-efficient windows installed in a modern home with natural light flooding in',
                    'details': 'crystal clear glass, sleek frames, view of beautiful outdoors, warm inviting interior',
                    'mood': 'bright, energy-efficient, home upgrade'
                },
                'garage_door': {
                    'scene': 'Stunning new modern garage door on a beautiful home, perfectly complementing the architecture',
                    'details': 'contemporary design, premium materials, excellent curb appeal, residential street setting',
                    'mood': 'curb appeal, home value, modern design'
                }
            }
            
            industry_data = industry_scenes.get(
                business_type.lower(), 
                {
                    'scene': f'Professional {business_type} service being performed by a skilled technician',
                    'details': 'clean professional environment, quality workmanship, satisfied customer',
                    'mood': 'professional, trustworthy, quality service'
                }
            )
            
            prompt_parts.append(industry_data['scene'])
            prompt_parts.append(industry_data['details'])
            
        else:
            # Use the topic if no business type specified
            prompt_parts.append(topic)
        
        # Add location context naturally
        if location:
            location_lower = location.lower()
            if any(fl in location_lower for fl in ['florida', 'sarasota', 'tampa', 'orlando', 'miami', 'fort myers']):
                prompt_parts.append('Florida setting with palm trees and bright sunshine visible')
            elif any(ca in location_lower for ca in ['california', 'los angeles', 'san diego', 'san francisco']):
                prompt_parts.append('California setting with beautiful weather and blue skies')
            elif any(tx in location_lower for tx in ['texas', 'houston', 'dallas', 'austin']):
                prompt_parts.append('Texas setting with spacious property and clear skies')
            elif any(az in location_lower for az in ['arizona', 'phoenix', 'scottsdale']):
                prompt_parts.append('Arizona desert setting with warm earth tones')
            # Add more regions as needed
        
        # Compose the final prompt as a natural description
        prompt = '. '.join(prompt_parts)
        
        return prompt


# Singleton instance
_image_service = None


def get_image_service() -> ImageGenerationService:
    """Get or create image generation service instance"""
    global _image_service
    if _image_service is None:
        _image_service = ImageGenerationService()
    return _image_service
