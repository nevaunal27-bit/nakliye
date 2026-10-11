import datetime
import pandas as pd
import streamlit as st

# --- SAF MERSİN LİMAN AKTARMA PARAMETRELERİ (KDV %16) ---
KDV_ORANI = 0.16

# 15 Eylül İtibariyle Geçerli Güncel Matrah Fiyat Listesi (Görselden Birebir İşlenen)
DEPO_FIYATLARI = {
    "ardep_dolu": 2000.0,
    "ardep_boş": 1900.0,
    "kahramanli_ardep_boş": 1950.0,
    "demireller_dolu": 2300.0,
    "demireller_boş": 2100.0,
    "falcon_dolu": 2100.0,
    "falcon_boş": 2000.0,
    "medlog_dolu": 2300.0,
    "medlog_boş": 2100.0,
    "gts_dolu": 2500.0,
    "gts_boş": 2100.0,
    "ardep_gts_emanet_dolu": 1900.0,
    "ols_dolu": 1950.0,
    "ols_boş": 1900.0,
    "ciss_dolu": 2200.0,
    "ciss_boş": 1950.0,
    "ccis_dolu": 2200.0,  # CISS ile aynı kabul edildi
    "ccis_boş": 1950.0,
    "sabanci_dolu": 2200.0,
    "sabanci_boş": 1950.0,
    "ardep_emanet_dolu": 1650.0,
    "oyak_depo_dolusu": 1700.0
}

# Güzergah Mesafe Verileri (A Noktası -> B Noktası Liman)
DEPO_MESAFELERI = {
    "gts": 8.0,
    "ardep": 6.0,
    "kahramanli": 8.5,
    "ccis": 9.0,
    "ciss": 9.0,
    "demirel": 7.0,
    "falcon": 7.0,
    "medlog": 7.5,
    "ols": 10.0,
    "sabanci": 11.0,
    "oyak": 12.0
}

# Şehiriçi Trafik ve Tonaj Tüketim Modellemesi
BASE_CONSUMPTION_EMPTY = 0.38  # Boş/Yüksüz tır: KM başına 0.38 Litre
BASE_CONSUMPTION_LOADED = 0.57  # Dolu tır (24-25 Ton Ağır Yük): KM başına 0.57 Litre

def calculate_real_consumption(distance, is_loaded, dt):
    base_rate = BASE_CONSUMPTION_LOADED if is_loaded else BASE_CONSUMPTION_EMPTY
    # Gündüz dur-kalk ve rölanti liman sırası bekleme çarpanı (%45 fazla tüketim)
    if 8 <= dt.hour <= 18:
        traffic_multiplier = 1.45
    else:
        traffic_multiplier = 1.00
    return distance * base_rate * traffic_multiplier

def is_normal_hour(dt: datetime.datetime) -> bool:
    """Haftaiçi 08-18, Cmt 08-13 arası normal prim (250 TL), diğer saatler çift (500 TL)."""
    weekday = dt.weekday()
    time_of_day = dt.time()
    if 0 <= weekday <= 4:
        return datetime.time(8, 0) <= time_of_day <= datetime.time(18, 0)
    elif weekday == 5:
        return datetime.time(8, 0) <= time_of_day <= datetime.time(13, 0)
    return False

def parse_whatsapp_smart_analytics_v4(text_content):
    seferler_list = []
    text_content = text_content.replace("\x00", "").replace("\ufeff", "").replace("\r", "")
    satirlar = text_content.split("\n")

    son_depo_tahmini = "gts"
    son_yuk_durumu = "dolu"
    
    son_sefer_zamani = {"Önal": None, "Salih": None, "Hasib": None}

    for satir in satirlar:
        satir = satir.strip()
        if not satir or " - " not in satir or ":" not in satir:
            continue

        satir_lower = satir.lower()

        # Soda işlerini tamamen yoksay
        if "soda" in satir_lower:
            continue

        # Akıllı Durum ve Depo Analizi
        for depo_anahtar in DEPO_MESAFELERI.keys():
            if depo_anahtar in satir_lower:
                son_depo_tahmini = depo_anahtar
                break
        
        if "boş" in satir_lower:
            son_yuk_durumu = "boş"
        elif "dolu" in satir_lower or "dolusu" in satir_lower:
            son_yuk_durumu = "dolu"

        # Resim veya hareket bildirimlerini yakala
        is_action = any(x in satir_lower for x in ["<medya dahil edilmedi>", "görsel", "teslim", "edildi", "ettim", "çıkış yaptım"])
        if not is_action:
            continue

        try:
            timestamp_part, remainder = satir.split(" - ", 1)
            sender_part, _ = remainder.split(":", 1)
        except:
            continue

        sender_lower = sender_part.lower()
        driver_name = ""
        if "önal" in sender_lower or "ünal" in sender_lower: driver_name = "Önal"
        elif "salih" in sender_lower: driver_name = "Salih"
        elif "hasib" in sender_lower or "selahattin" in sender_lower: driver_name = "Hasib"

        if not driver_name:
            continue

        try:
            timestamp_clean = timestamp_part.replace("[", "").replace("]", "").strip()
            dt = datetime.datetime.strptime(timestamp_clean, "%d.%m.%Y %H:%M")
        except:
            continue

        # Aynı şoförün 60 dakika içindeki mükerrer mesajlarını/resimlerini tek sefer sayar
        if son_sefer_zamani[driver_name] is not None:
            dakika_farki = (dt - son_sefer_zamani[driver_name]).total_seconds() / 60
            if dakika_farki < 60:
                continue

        son_sefer_zamani[driver_name] = dt

        # Fiyat Listesi Anahtar Kombinasyon Eşleştirmesi
        fiyat_key = f"{son_depo_tahmini}_{son_yuk_durumu}"
        
        # İstisnai Kombinasyon Çözümleri
        if "kahraman" in satir_lower and "boş" in satir_lower: fiyat_key = "kahramanli_ardep_boş"
        elif "ardep" in satir_lower and "gts" in satir_lower and "emanet" in satir_lower: fiyat_key = "ardep_gts_emanet_dolu"
        elif "ardep" in satir_lower and "emanet" in satir_lower: fiyat_key = "ardep_emanet_dolu"
        elif "oyak" in satir_lower: fiyat_key = "oyak_depo_dolusu"

        # Eğer tam kombinasyon yoksa varsayılana dön
        if fiyat_key not in DEPO_FIYATLARI:
            fiyat_key = "gts_dolu"

        # Hesaplamalar
        is_normal = is_normal_hour(dt)
        final_premium = 250 if is_normal else 500
        
        km = DEPO_MESAFELERI.get(son_depo_tahmini, 8.0)
        is_loaded_bool = (son_yuk_durumu == "dolu")
        harcanan_litre = calculate_real_consumption(km, is_loaded_bool, dt)
        
        matrah = DEPO_FIYATLARI[fiyat_key]
        brut_ciro = matrah * (1 + KDV_ORANI)

        seferler_list.append({
            "Şoför": driver_name,
            "Tarih/Saat": dt,
            "Güzergah Hat Değeri": fiyat_key.upper().replace("_", " "),
            "Mesafe (KM)": km,
            "Hesaplanan Tüketim (Litre)": round(harcanan_litre, 2),
            "Şoför Primi (TL)": final_premium,
            "Sefer Cirosu (TL)": brut_ciro,
            "Trafik Durumu": "Gündüz (Yoğun Trafik)" if (8 <= dt.hour <= 18) else "Gece / Akşam (Akıcı)"
        })

    return pd.DataFrame(seferler_list)


# --- STREAMLIT PC PANEL TASARIMI ---
st.set_page_config(page_title="Mersin Liman İçi Aktarma Analitiği", layout="wide")
st.title("📊 Mersin Şehiriçi Konteynır Karlılık & Verimlilik Analiz Motoru")
st.caption("Güncel 15 Eylül Fiyat Tarifesi ve Kesinleşmiş Ciro Endeks Modeli")

st.sidebar.header("⛽ Hassas Yakıt ve Depo Girişleri")
manuel_litre_fiyati = st.sidebar.number_input("Güncel Mazot Litre Fiyatı (TL)", min_value=0.0, value=43.15)
manuel_alinan_litre = st.sidebar.number_input("Dönem İçi Toplam Alınan Toplam Mazot (Litre)", min_value=0.0, value=1200.0)
depodaki_mevcut_litre = st.sidebar.number_input("Şu Anda Depolarda Kalan Toplam Yakıt (Litre)", min_value=0.0, value=150.0)

# Sabit Giderler
SABIT_SIGORTA_AYLIK = 82000 / 12
SABIT_PERSONEL_AYLIK = 42000 + 12000
SABIT_SANAYI_AYLIK = 600000 / 3 / 12
TOPLAM_AYLIK_SABIT_GIDER_TIR_BASI = SABIT_SIGORTA_AYLIK + SABIT_PERSONEL_AYLIK + SABIT_SANAYI_AYLIK

st.sidebar.markdown("---")
st.sidebar.subheader("📅 Sabit Gider Payı")
st.sidebar.write(f"3 Araç Toplam Aylık Gider: **{TOPLAM_AYLIK_SABIT_GIDER_TIR_BASI * 3:,.2f} TL**")

whatsapp_file = st.file_uploader("WhatsApp .txt Sohbet Dosyasını Sürükleyip Bırakın", type=["txt"])

if whatsapp_file is not None:
    chat_text = whatsapp_file.read().decode("utf-8", errors="ignore")
    df = parse_whatsapp_smart_analytics_v4(chat_text)

    if not df.empty:
        st.success(f"✅ Analiz Başarılı! {len(df)} adet net liman aktarma seferi, 15 Eylül fiyat listesiyle kuruşu kuruşuna hesaplandı.")

        # --- ÜST ÖZET FINANSAL KARTLAR ---
        total_ciro = df["Sefer Cirosu (TL)"].sum()
        total_prim = df["Şoför Primi (TL)"].sum()
        
        gercek_tuketilen_yakit = manuel_alinan_litre - depodaki_mevcut_litre
        gercek_yakit_maliyeti = gercek_tuketilen_yakit * manuel_litre_fiyati
        net_yol_kari = total_ciro - total_prim - gercek_yakit_maliyeti

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Brüt Ciro (KDV Dahil)", f"{total_ciro:,.2f} TL")
        col2.metric("Toplam Şoför Primleri", f"{total_prim:,.2f} TL")
        col3.metric("Gerçek Yakıt Maliyeti", f"{gercek_yakit_maliyeti:,.2f} TL", f"{gercek_tuketilen_yakit:,.1f} L Sarfiyat")
        col4.metric("Net Yol Kârı", f"{net_yol_kari:,.2f} TL")

        # --- GÜZERGAH KÂRLILIK KARNESİ ---
        st.subheader("🎯 Güzergah Bazlı Sefer Net Kâr Analizi")
        
        df_group = df.groupby("Güzergah Hat Değeri").agg(
            Sefer_Sayisi=("Şoför", "count"),
            Toplam_Ciro=("Sefer Cirosu (TL)", "sum"),
            Toplam_Prim=("Şoför Primi (TL)", "sum"),
            Tahmini_Litre_Tuketimi=("Hesaplanan Tüketim (Litre)", "sum")
        ).reset_index()
        
        df_group["Modellenen Yakıt Maliyeti (TL)"] = df_group["Tahmini_Litre_Tuketimi"] * manuel_litre_fiyati
        df_group["Net Bırakılan Kâr (TL)"] = df_group["Toplam_Ciro"] - df_group["Toplam_Prim"] - df_group["Modellenen Yakıt Maliyeti (TL)"]
        df_group["Sefer Başı Ortalama Kâr (TL)"] = df_group["Net Bırakılan Kâr (TL)"] / df_group["Sefer_Sayisi"]
        
        df_group = df_group.sort_values(by="Sefer Başı Ortalama Kâr (TL)", ascending=False)
        
        st.dataframe(df_group[[
            "Güzergah Hat Değeri", "Sefer_Sayisi", "Toplam_Ciro", "Net Bırakılan Kâr (TL)", "Sefer Başı Ortalama Kâr (TL)"
        ]], use_container_width=True)
        
        # En karlı güzergah çıktısı
        if not df_group.empty:
            en_karli_rota = df_group.iloc[0]["Güzergah Hat Değeri"]
            st.info(
                f"🧠 **Yapay Zeka Stratejik Raporu:** 15 Eylül fiyat tarifesi ve Mersin şehiriçi trafik çarpanları analizine göre, "
                f"operasyonunuzda sefer başına en yüksek net verimliliği ve nakit kârı **{en_karli_rota}** hattı sağlamaktadır."
            )

        st.subheader("📋 Sefer Sefer Detaylı Trafik ve Tüketim Analiz Listesi")
