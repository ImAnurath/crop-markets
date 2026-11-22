"""Plotly locale definitions, handed to plotly.js per chart as ``config.locales``.

Data copied from plotly.js 4.1.1's ``dist/plotly-locale-tr.js`` (the plotly.js bundled
with plotly 7.1.0, pinned in requirements-site.txt), converted to Python without change:
https://cdn.plot.ly/plotly-locale-tr-4.1.1.js
sha256 a8a14447912f293643ac34b671f393fd723b5a21249dbd5b8f1753940203bc93

``test_plotly_locales_match_bundled_plotlyjs`` fails when the bundled plotly.js version
changes: copy the locale of the new version, then update ``PLOTLY_JS_VERSION``.
"""

PLOTLY_JS_VERSION = "4.1.1"

LOCALES: dict[str, dict] = {
    "tr": {
        "dictionary": {
            "Autoscale": "Otomatik Ölçeklendir",
            "Box Select": "Dikdörtgen Kutu Seçimi",
            "Click to enter Colorscale title": "Renk Ölçeği başlığını girmek için tıklayın",
            "Click to enter Component A title": "A bileşeni başlığını girmek için tıklayın",
            "Click to enter Component B title": "B bileşeni başlığını girmek için tıklayın",
            "Click to enter Component C title": "C bileşeni başlığını girmek için tıklayın",
            "Click to enter Plot title": "Grafik başlığını girmek için tıklayın",
            "Click to enter X axis title": "X ekseni başlığını girmek için tıklayın",
            "Click to enter Y axis title": "Y ekseni başlığını girmek için tıklayın",
            "Compare data on hover": "Üzerine gelince verileri karşılaştır",
            "Double-click on legend to isolate one trace": "Bir izi izole etmek için göstergeye (legend) çift tıklayın",
            "Double-click to zoom back out": "Geri uzaklaştırmak için çift tıklayın",
            "Download plot as a PNG": "Grafiği PNG olarak indir",
            "Download plot": "Grafiği indir",
            "Edit in Chart Studio": "Chart Studio'da düzenle",
            "IE only supports svg.  Changing format to svg.": "IE yalnızca svg'yi destekler. Format svg'ye dönüştürülüyor.",
            "Lasso Select": "Serbest seçim",
            "Orbital rotation": "Yörüngesel döndürme",
            "Pan": "Kaydır",
            "Produced with Plotly.js": "Plotly.js ile üretilmiştir",
            "Reset": "Sıfırla",
            "Reset axes": "Eksenleri sıfırla",
            "Reset camera to default": "Kamerayı varsayılana sıfırla",
            "Reset camera to last save": "Kamerayı son kaydedilene sıfırla",
            "Reset view": "Görünümü sıfırla",
            "Reset views": "Görünümleri sıfırla",
            "Show closest data on hover": "Üzerine gelince en yakın veriyi göster",
            "Image download succeeded": "Görüntü indirme başarılı",
            "Sorry, there was a problem downloading your image!": "Üzgünüz, görüntünüz indirilirken bir sorun oluştu!",
            "Preparing image - this may take a few seconds": "Görüntü hazırlanıyor - bu işlem birkaç saniye sürebilir",
            "Zoom": "Yakınlaştır",
            "Zoom in": "Yakınlaş",
            "Zoom out": "Uzaklaş",
            "close:": "kapanış:",
            "trace": "iz",
            "lat:": "enlem:",
            "lon:": "boylam:",
            "q1:": "ç1:",
            "q3:": "ç3:",
            "source:": "kaynak:",
            "target:": "hedef:",
            "lower fence:": "alt sınır:",
            "upper fence:": "üst sınır:",
            "max:": "maks:",
            "mean ± σ:": "ortalama ± σ:",
            "mean:": "ortalama:",
            "median:": "medyan:",
            "min:": "min:",
            "Turntable rotation": "Döner tabla (turntable) dönüşü",
            "Toggle Spike Lines": "Yardımcı Çizgileri Aç/Kapat",
            "open:": "açılış:",
            "high:": "yüksek:",
            "low:": "düşük:",
            "Toggle show closest data on hover": "Üzerine gelince en yakın veriyi gösterme seçeneğini aç/kapat",
            "incoming flow count:": "gelen akış sayısı:",
            "outgoing flow count:": "giden akış sayısı:",
            "kde:": "çekirdek yoğunluk tahmini (kde):"
        },
        "format": {
            "days": [
                "Pazar",
                "Pazartesi",
                "Salı",
                "Çarşamba",
                "Perşembe",
                "Cuma",
                "Cumartesi"
            ],
            "shortDays": [
                "Pz",
                "Pt",
                "Sa",
                "Ça",
                "Pe",
                "Cu",
                "Ct"
            ],
            "months": [
                "Ocak",
                "Şubat",
                "Mart",
                "Nisan",
                "Mayıs",
                "Haziran",
                "Temmuz",
                "Ağustos",
                "Eylül",
                "Ekim",
                "Kasım",
                "Aralık"
            ],
            "shortMonths": [
                "Oca",
                "Şub",
                "Mar",
                "Nis",
                "May",
                "Haz",
                "Tem",
                "Ağu",
                "Eyl",
                "Eki",
                "Kas",
                "Ara"
            ],
            "date": "%d.%m.%Y",
            "decimal": ",",
            "thousands": "."
        }
    },
}
