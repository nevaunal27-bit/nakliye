import datetime
import pandas as pd
import streamlit as st

# --- SAF MERSİN LİMAN AKTARMA PARAMETRELERİ (KDV %16) ---
KDV_ORANI = 0.16

# 15 Eylül İtibariyle Geçerli Güncel Matrah Fiyat Listesi
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
    "ccis_dolu": 2200.0,
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
BASE_CONSUMPTION_EMPTY = 0.38  
BASE_CONSUMPTION_LOADED = 0.57  

def calculate_real_consumption(distance, is_loaded, dt):
    base_rate = BASE_CONSUMPTION_LOADED if is_loaded else BASE_CONSUMPTION_EMPTY
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

def get_custom_operational_week(dt):
    """Pazartesi 08:00 ile bir sonraki Pazar 08:00 arasını lojistik haftası kabul eder."""
    # O haftanın Pazartesi gününü bul
    monday = dt - datetime.timedelta(days=dt.weekday())
    monday_08 = datetime.datetime.combine(monday.date(), datetime.time(8, 0))
    
    # Eğer mevcut mesaj Pazartesi 08:00'den önceyse, bir önceki operasyonel haftaya aittir
    if dt < monday_08:
        monday_08 = monday_08 - datetime.timedelta(days=7)
        
    sunday_08_end = monday_08 + datetime.timedelta(days=6)
    return f"{monday_08.strftime('%d/%m')} ➡️ {sunday_08_end.strftime('%d/%m')} Haftası"

def parse_whatsapp_smart_analytics_v6(text_content):
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

        if "soda" in satir_lower:
            continue

        for depo_anahtar in DEPO_MESAFELERI.keys():
            if depo_anahtar in satir_lower:
                son_depo_tahmini = depo_anahtar
                break
        
        if "boş" in satir_lower:
            son_yuk_durumu = "boş"
        elif "dolu" in satir_lower or "dolusu" in satir_lower:
            son_yuk_durumu = "dolu"

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

        if son_sefer_zamani[driver_name] is not None:
            dakika_farki = (dt - son_sefer_zamani[driver_name]).total_seconds() / 60
            if dakika_farki < 60:
                continue

        son_sefer_zamani[driver_name] = dt

        fiyat_key = f"{son_depo_tahmini}_{son_yuk_durumu}"
        
        if "kahraman" in satir_lower and "boş" in satir_lower: fiyat_key = "kahramanli_ardep_boş"
        elif "ardep" in satir_lower and "gts" in satir_lower and "emanet" in satir_lower: fiyat_key = "ardep_gts_emanet_dolu"
        elif "ardep" in satir_lower and "emanet" in satir_lower: fiyat_key = "ardep_emanet_dolu"
        elif "oyak" in satir_lower: fiyat_key = "oyak_depo_dolusu"

        if fiyat_key not in DEPO_FIYATLARI:
            fiyat_key = "gts_dolu"

        is_normal = is_normal_hour(dt)
        final_premium = 250 if is_normal else 500
        
        km = DEPO_MESAFELERI.get(son_depo_tahmini, 8.0)
        is_loaded_bool = (son_yuk_durumu == "dolu")
        harcanan_litre = calculate_real_consumption(km, is_loaded_bool, dt)
        
        matrah = DEPO_FIYATLARI[fiyat_key]
        brut_ciro = matrah * (1 + KDV_ORANI)

        seferler_list.append({
            "Şoför": driver_name,
            "Tarih / Saat": dt.strftime("%d/%m/%Y %H:%M"),
            "dt_object": dt,
            "Lojistik Haftası": get_custom_operational_week(dt),
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
st.caption("2 Aktif Araç Üzerinden Gün Bazlı Gider Dağılımlı Lojistik Yönetim Paneli")

st.sidebar.header("⛽ Hassas Yakıt Girişleri")
manuel_litre_fiyati = st.sidebar.number_input("Güncel Mazot Litre Fiyatı (TL)", min_value=0.0, value=86.50)
manuel_alinan_litre = st.sidebar.number_input("Dönem İçi Toplam Alınan Mazot (Litre)", min_value=0.0, value=979.0)
depodaki_mevcut_litre = st.sidebar.number_input("Şu Anda Çekicilerin Deposunda Kalan Yakıt (Litre)", min_value=0.0, value=250.0)

# --- ARAÇ BAŞI SABIT GIDER HESAPLAMA MOTORU ---
GUNLUK_SABIT_GIDER_PER_ARAC = ((82000 + 200000) / 365) + ((42000 + 12000) / 30)
AKTIF_ARAC_SAYISI = 2
TOPLAM_SIRKET_GUNLUK_GIDERI = GUNLUK_SABIT_GIDER_PER_ARAC * AKTIF_ARAC_SAYISI

st.sidebar.markdown("---")
st.sidebar.subheader("📅 Gün Bazlı Gider Bilgisi")
st.sidebar.write(f"Araç Başı Günlük Gider: **{GUNLUK_SABIT_GIDER_PER_ARAC:,.2f} TL**")
st.sidebar.write(f"2 Araç Toplam Günlük Gider: **{TOPLAM_SIRKET_GUNLUK_GIDERI:,.2f} TL**")
st.sidebar.caption("*(Sigorta, Sanayi, Maaş ve SGK kalemlerinin güne vurulmuş net halidir)*")

whatsapp_file = st.file_uploader("WhatsApp .txt Sohbet Dosyasını Sürükleyip Bırakın", type=["txt"])

if whatsapp_file is not None:
    chat_text = whatsapp_file.read().decode("utf-8", errors="ignore")
    df = parse_whatsapp_smart_analytics_v6(chat_text)

    if not df.empty:
        st.success("✅ Analiz Başarılı! Net liman aktarma seferleri kuruşu kuruşuna hesaplandı.")

        # --- DÖNEM GÜN SAYISI BULMA VE SABİT GİDERİ GÜNLÜK PAYA ÇEVİRME ---
        df["dt_object"] = pd.to_datetime(df["dt_object"])
        min_date = df["dt_object"].min()
        max_date = df["dt_object"].max()
        gun_sayisi = (max_date - min_date).days
        if gun_sayisi < 1: 
            gun_sayisi = 1  
            
        # Toplam Dönemlik Sabit Gider Payı
        donemlik_sabit_gider_payi = TOPLAM_SIRKET_GUNLUK_GIDERI * gun_sayisi

        # --- ÜST ÖZET FINANSAL KARTLAR ---
        total_ciro = df["Sefer Cirosu (TL)"].sum()
        total_prim = df["Şoför Primi (TL)"].sum()
        
        gercek_tuketilen_yakit = manuel_alinan_litre - depodaki_mevcut_litre
        gercek_yakit_maliyeti = gercek_tuketilen_yakit * manuel_litre_fiyati
        
        # Net Şirket Kârı Hesaplaması
        net_sirket_kari = total_ciro - total_prim - gercek_yakit_maliyeti - donemlik_sabit_gider_payi

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Toplam Brüt Ciro (KDV Dahil)", f"{total_ciro:,.2f} TL")
        col2.metric("Toplam Şoför Primleri", f"{total_prim:,.2f} TL")
        col3.metric("Gerçek Yakıt Maliyeti", f"{gercek_yakit_maliyeti:,.2f} TL", f"{gercek_tuketilen_yakit:,.1f} L Sarfiyat")
        col4.metric("Şirket Net Kârı", f"{net_sirket_kari:,.2f} TL", f"{gun_sayisi} Günlük Gider Dağıtıldı (-{donemlik_sabit_gider_payi:,.2f} TL)")

        # --- YENİ MODÜL: HAFTALIK ŞOFÖR PRİM TAKİP EKRANI ---
        st.subheader("💵 Haftalık Şoför Prim Takip Ekranı")
        st.caption("Pazartesi 08:00'den bir sonraki Pazar 08:00'e kadar olan dönemlik hakedişlerdir:")
        
        df_weekly = df.groupby(["Lojistik Haftası", "Şoför"]).agg(
            Toplam_Sefer=("Güzergah Hat Değeri", "count"),
            Toplam_Hakedis_Prim=("Şoför Primi (TL)", "sum")
        ).reset_index()
        
        # Tabloyu daha şık ve scannable göstermek için yan yana pivot tablo biçimine çevirelim
        df_weekly_pivot = df_weekly.pivot(index="Lojistik Haftası", columns="Şoför", values="Toplam_Hakedis_Prim").fillna(0)
        st.dataframe(df_weekly_pivot, use_container_width=True)

