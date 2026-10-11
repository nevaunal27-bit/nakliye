import datetime
import pandas as pd
import streamlit as st

# --- MERSİN ŞEHİR İÇİ LİMAN AKTARMA PARAMETRELERİ (KDV %16) ---
KDV_ORANI = 0.16

# Rotaların Tamamı: Depo <-> Liman Arasıdır (Matrah Fiyatlar)
DEPO_FIYATLARI = {
    "ardep": 3800.0,
    "gts": 3600.0,
    "ccis": 3700.0,
    "ciss": 3700.0,
    "demirel": 3500.0,
    "falcon": 3500.0,
    "ols": 3400.0
}

# Depoların Limana Olan Gerçek Karayolu Mesafeleri (A Noktası -> Liman B Noktası)
DEPO_MESAFELERI = {
    "ardep": 6.0,    # Ardep - Liman: 6 KM
    "gts": 8.0,      # GTS - Liman: 8 KM
    "ccis": 9.0,     # CCIS - Liman: 9 KM
    "ciss": 9.0,     # CISS - Liman: 9 KM
    "demirel": 7.0,  # Demireller - Liman: 7 KM
    "falcon": 7.0,   # Falcon - Liman: 7 KM
    "ols": 10.0      # OLS - Liman: 10 KM
}

# --- REALİSTİK ŞEHİR İÇİ TÜKETİM MODELİ ---
BASE_CONSUMPTION_EMPTY = 0.38  # Boş/Yüksüz tır: KM başına 0.38 Litre
BASE_CONSUMPTION_LOADED = 0.57  # Dolu tır (24-25 Ton Ağır Yük): KM başına 0.57 Litre

def calculate_real_consumption(distance, is_loaded, dt):
    """Mersin şehir içi trafik, dur-kalk ve liman sıra bekleme sürelerini hesaplar."""
    base_rate = BASE_CONSUMPTION_LOADED if is_loaded else BASE_CONSUMPTION_EMPTY
    
    # Gündüz mesai saatlerinde liman trafiği ve rölanti tüketimi %45 artar
    if 8 <= dt.hour <= 18:
        traffic_multiplier = 1.45
    else:
        traffic_multiplier = 1.00  # Gece ve akşam akıcı trafik
        
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

def parse_whatsapp_clean_trucks(text_content):
    seferler = []
    text_content = text_content.replace("\x00", "").replace("\ufeff", "").replace("\r", "")
    satirlar = text_content.split("\n")

    son_depo_tahmini = "gts"
    son_yuk_durumu = False 

    for satir in satirlar:
        satir = satir.strip()
        if not satir or " - " not in satir or ":" not in satir:
            continue

        satir_lower = satir.lower()

        # 1. KURAL: SODA İLE İLGİLİ HER ŞEYİ TAMAMEN YOK SAY VE ATLA
        if "soda" in satir_lower:
            continue

        # Yazışmalardan aktif depoyu (A Noktası) ve yük durumunu çek
        for depo in DEPO_FIYATLARI.keys():
            if depo in satir_lower:
                son_depo_tahmini = depo
                break
        
        if "dolu" in satir_lower:
            son_yuk_durumu = True
        elif "boş" in satir_lower:
            son_yuk_durumu = False

        # Sadece resim paylaşılan veya net iş bildirim satırlarını işleme al
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

        # Prim kuralları (Sadece 250 TL normal, 500 TL çift prim)
        is_normal = is_normal_hour(dt)
        multiplier = 1 if is_normal else 2
        final_premium = 250 * multiplier

        # Mesafe ve Tüketim Hesaplama (Depo <-> Liman)
        km = DEPO_MESAFELERI[son_depo_tahmini]
        harcanan_litre = calculate_real_consumption(km, son_yuk_durumu, dt)
        ciro = DEPO_FIYATLARI[son_depo_tahmini] * (1 + KDV_ORANI)

        seferler.append({
            "Şoför": driver_name,
            "Tarih/Saat": dt,
            "Güzergah (A -> B)": f"{son_depo_tahmini.upper()} <-> LİMAN",
            "Yük Durumu": "DOLU (24 Ton)" if son_yuk_durumu else "BOŞ / YÜKSÜZ",
            "Mesafe (KM)": km,
            "Hesaplanan Tüketim (Litre)": round(harcanan_litre, 2),
            "Şoför Primi (TL)": final_premium,
            "Sefer Cirosu (TL)": ciro,
            "Trafik Durumu": "Gündüz (Yoğun Trafik)" if (8 <= dt.hour <= 18) else "Gece / Akşam (Akıcı)"
        })

    return pd.DataFrame(seferler)


# --- STREAMLIT PC PANEL TASARIMI ---
st.set_page_config(page_title="Mersin Liman İçi Aktarma Analitiği", layout="wide")
st.title("📊 Mersin Şehiriçi Konteynır Karlılık & Verimlilik Analiz Motoru")
st.caption("Soda Operasyonları Hariç - Saf Liman Aktarma Modeli")

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

whatsapp_file = st.file_uploader("WhatsApp .txt Sohbet Dosyasını Bilgisayarınızdan Sürükleyin veya Seçin", type=["txt"])

if whatsapp_file is not None:
    chat_text = whatsapp_file.read().decode("utf-8", errors="ignore")
    df = parse_whatsapp_clean_trucks(chat_text)

    if not df.empty:
        st.success(f"✅ Akıllı okuma tamamlandı! {len(df)} adet saf liman aktarma seferi analiz edildi.")

        # --- ÜST ÖZET FINANSAL KARTLAR ---
        total_ciro = df["Sefer Cirosu (TL)"].sum()
        total_prim = df["Şoför Primi (TL)"].sum()
        
        # Gerçek tüketim ve maliyet hesabı
        gercek_tuketilen_yakit = manuel_alinan_litre - depodaki_mevcut_litre
        gercek_yakit_maliyeti = gercek_tuketilen_yakit * manuel_litre_fiyati
        net_yol_kari = total_ciro - total_prim - gercek_yakit_maliyeti

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Saf Liman Cirosu", f"{total_ciro:,.2f} TL")
        col2.metric("Toplam Şoför Primleri", f"{total_prim:,.2f} TL")
        col3.metric("Gerçek Tüketilen Yakıt Maliyeti", f"{gercek_yakit_maliyeti:,.2f} TL", f"{gercek_tuketilen_yakit:,.1f} L Tüketim")
        col4.metric("Net Yol Kârı", f"{net_yol_kari:,.2f} TL")

        # --- GÜZERGAH KÂRLILIK KARNESİ ---
        st.subheader("🎯 Güzergah Bazlı Sefer Net Kâr Analizi")
        
        df_group = df.groupby("Güzergah (A -> B)").agg(
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
            "Güzergah (A -> B)", "Sefer_Sayisi", "Toplam_Ciro", "Net Bırakılan Kâr (TL)", "Sefer Başı Ortalama Kâr (TL)"
        ]], use_container_width=True)
        
        if len(df_group) > 0:
            en_karli_rota = df_group.iloc[0]["Güzergah (A -> B)"]
            st.info(
                f"🧠 **Yapay Zeka Strateji Raporu:** Soda yükleri hariç tutulduğunda, Mersin şehir içi trafiği ve tonaj ağırlığı "
                f"analizine göre tırlarınız için sefer başına en yüksek net verimliliği ve kazancı **{en_karli_rota}** rotası sağlamaktadır."
            )

        st.subheader("📋 Sefer Sefer Detaylı Trafik ve Tüketim Analiz Listesi")
        st.dataframe(df[["Şoför", "Güzergah (A -> B)", "Yük Durumu", "Trafik Durumu", "Hesaplanan Tüketim (Litre)", "Şoför Primi (TL)", "Sefer Cirosu (TL)"]], use_container_width=True)
    else:
        st.error("Yüklenen dosya okundu ancak içerisinde soda harici geçerli bir liman aktarma güzergahı bulunamadı.")
