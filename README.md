# ✨ PixelOff - Instagram Arkaplan Temizleyici

Bu araç, verdiğiniz Instagram linkindeki fotoğrafı indirir ve yapay zeka kullanarak arkaplanını şeffaf hale getirir.
Canva kullanmadan, kendi bilgisayarınızda saniyeler içinde sonuç almanızı sağlar.

## Kurulum

Öncelikle gerekli kütüphaneleri yükleyin:

```bash
pip install -r requirements.txt
```

> **Not:** `rembg` ilk çalıştırıldığında gerekli yapay zeka modelini (yaklaşık 100MB) indirecektir. İnternet bağlantınızın açık olduğundan emin olun.

## Kullanım

Aracı çalıştırmak için terminalde aşağıdaki komutu kullanın:

```bash
python main.py <INSTAGRAM_LINKI>
```

Örnek:

```bash
python main.py https://www.instagram.com/p/CpKQ8qXt0yO/
```

## Sonuç

İşlem tamamlandığında:
1. Fotoğraf `downloads/` klasörüne indirilir.
2. Arkaplanı silinmiş hali aynı klasörde `..._nobg.png` olarak kaydedilir.
