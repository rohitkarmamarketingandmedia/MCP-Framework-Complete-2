# Fonts for Featured Image Generation

The featured image generator uses these fonts for text overlays.

## Required Fonts

Place the following font files in this directory:

1. **Montserrat-Bold.ttf** (preferred)
   - Download from: https://fonts.google.com/specimen/Montserrat
   
2. **DejaVuSans-Bold.ttf** (fallback)
   - Usually available in `/usr/share/fonts/truetype/dejavu/`

## Fallback Behavior

If no fonts are found, the system will try:
1. System fonts (DejaVu, Liberation, Helvetica, Arial)
2. PIL default font (basic, not recommended)

## Installation

```bash
# Ubuntu/Debian - install DejaVu fonts
apt-get install fonts-dejavu

# Or download Montserrat
wget https://github.com/JulietaUla/Montserrat/raw/master/fonts/ttf/Montserrat-Bold.ttf
mv Montserrat-Bold.ttf static/fonts/
```
