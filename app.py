import datetime
import pandas as pd
import streamlit as st

# --- SAF MERSİN LİMAN AKTARMA PARAMETRELERİ (KDV %16) ---
KDV_ORANI = 0.16

DEPO_FIYATLARI = {
    "ardep_dolu": 2000.0, "ardep_boş": 1900.0, "kahramanli_ardep_boş": 1950.0,
    "demireller_dolu": 2300.0, "demireller_boş": 2100.0, "falcon_dolu": 2100.0,
    "falcon_boş": 2000.0, "medlog_dolu": 2300.0, "medlog_boş": 2100.0,
    "gts_dolu": 2500.0, "gts_boş": 2100.0, "ardep_gts_emanet_dolu": 1900.0,
    "ols_dolu": 1950.0, "ols_boş": 1900.0, "ciss_dolu": 2200.0, "ciss_boş": 1950.0,
    "ccis_dolu": 2200.0, "ccis_boş": 1950.0, "sabanci_dolu": 2200.0, "sabanci_boş": 1950.0,
    "ardep_emanet_dolu": 1650.0, "oyak_depo_dolusu": 1700.0
}

DEPO_MESAFELERI = {
    "gts": 8.0, "ardep": 6.0, "kahramanli": 8.5, "ccis": 9.0, "ciss": 9.0,
    "demirel": 7.0, "falcon": 7.0, "medlog": 7.5, "ols": 10.0, "sabanci": 11.0, "oyak": 12.0
}

# --- YAKIT TÜKETİM MODELİ ---
BASE_CONSUMPTION_EMPTY = 0.38   # Tamamen boş sal kasa veya boş konteynır: 100 KM'de 38 Litre
BASE_CONSUMPTION_LOADED = 0.57  # Dolu tır (24-25 Ton Ağır Yük): 100 KM'de 57 Litre

def calculate_real_consumption(distance, is_loaded, dt):
    base_rate = BASE_CONSUMPTION_LOADED if is_loaded else BASE_CONSUMPTION_EMPTY
    if 8 <= dt.hour <= 18:
        traffic_multiplier = 1.45  # Gündüz liman içi dur-kalk ve rölanti sırası
    else:
        traffic_multiplier = 1.00  # Gece akıcı trafik
    return distance * base_rate * traffic_multiplier

def is_normal_hour(dt: datetime.datetime) -> bool:
    weekday = dt.weekday()
    time_of_day = dt.time()
    if 0 <= weekday <= 4:
        return datetime.time(8, 0) <= time_of_day <= datetime.time(18, 0)
    elif weekday == 5:
        return datetime.time(8, 0) <= time_of_day <= datetime.time(13, 0)
    return False

def get_custom_operational_week(dt):
    monday = dt - datetime.timedelta(days=dt.weekday())
    monday_08 = datetime.datetime.combine(monday.date(), datetime.time(8, 0))
    if dt < monday_08:
        monday_08 = monday_08 - datetime.timedelta(days=7)
    sunday_08_end = monday_08 + datetime.timedelta(days=6)
    return f"{monday_08.strftime('%d/%m')} ➡️ {sunday_08_end.strftime('%d/%m')} Haftası"

def parse_single_source(text_content, force_driver=None):
    seferler_list = []
    text_content = text_content.replace("\x00", "").replace("\ufeff", "").replace("\r", "")
    satirlar = text_content.split("\n")

    son_depo_tahmini = "gts"
    son_yuk_durumu = "dolu"

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

        if force_driver:
            driver_name = force_driver
        else:
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

        fiyat_key = f"{son_depo_tahmini}_{son_yuk_durumu}"
        if "kahraman" in satir_lower and "boş" in satir_lower: fiyat_key = "kahramanli_ardep_boş"
        elif "ardep" in satir_lower and "gts" in satir_lower and "emanet" in satir_lower: fiyat_key = "ardep_gts_emanet_dolu"
        elif "ardep" in satir_lower and "emanet" in satir_lower: fiyat_key = "ardep_emanet_dolu"
        elif "oyak" in satir_lower: fiyat_key = "oyak_depo_dolusu"

        if fiyat_key not in DEPO_FIYATLARI:
            fiyat_key = "gts_dolu"

        is_normal = is_normal_hour(dt)
        final_premium = float(250 if is_normal else 500)
        
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
            "Depo_Kodu": son_depo_tahmini,
            "Yük_Durumu_Kodu": son_yuk_durumu,
            "Mesafe (KM)": km,
            "Hesaplanan Tüketim (Litre)": round(harcanan_litre, 2),
            "Şoför Primi (TL)": final_premium,
            "Sefer Cirosu (TL)": brut_ciro,
            "Trafik Durumu": "Gündüz (Yoğun Trafik)" if (8 <= dt.hour <= 18) else "Gece / Akşam (Akıcı)"
        })

    return pd.DataFrame(seferler_list)


# --- STREAMLIT PANEL TASARIMI ---
st.set_page_config(page_title="Mersin Liman İçi Aktarma Analitiği", layout="wide")
st.title("📊 Mersin Şehiriçi Konteynır Karlılık & Verimlilik Analiz Motoru")
st.caption("Sal Kasa Boş Kilometre ve Teyitli Çift Kanal Analiz Sistemi")

st.sidebar.header("⛽ Hassas Yakıt Girişleri")
manuel_litre_fiyati = st.sidebar.number_input("Güncel Mazot Litre Fiyatı (TL)", min_value=0.0, value=86.50)
manuel_alinan_litre = st.sidebar.number_input("Dönem İçi Toplam Alınan Mazot (Litre)", min_value=0.0, value=979.0)
depodaki_mevcut_litre = st.sidebar.number_input("Şu Anda Çekicilerin Deposunda Kalan Yakıt (Litre)", min_value=0.0, value=250.0)

st.sidebar.markdown("---")
st.sidebar.header("🚛 Filo Gider Ayarları")
aktif_arac_sayisi = st.sidebar.number_input("Şu Anda Aktif Çalışan Tır Sayısı", min_value=1, max_value=3, value=2)

GUNLUK_SABIT_GIDER_PER_ARAC = ((82000 + 200000) / 365) + ((42000 + 12000) / 30)
TOPLAM_SIRKET_GUNLUK_GIDERI = GUNLUK_SABIT_GIDER_PER_ARAC * aktif_arac_sayisi

st.sidebar.subheader("📅 Gün Bazlı Gider Bilgisi")
st.sidebar.write(f"Araç Başı Günlük Gider: **{GUNLUK_SABIT_GIDER_PER_ARAC:,.2f} TL**")
st.sidebar.write(f"{aktif_arac_sayisi} Araç Toplam Günlük Gider: **{TOPLAM_SIRKET_GUNLUK_GIDERI:,.2f} TL**")

st.subheader("📂 Akıllı Veri Giriş Kaynakları (3 Farklı Kanal)")
col_a, colb, colc = st.columns(3)

with col_a:
    grup_file = st.file_uploader("1. Ana Lojistik Grubu Dökümü (.txt)", type=["txt"], key="src_grup")
with colb:
    salih_file = st.file_uploader("2. Şoför Salih Özel Sohbeti (.txt)", type=["txt"], key="src_salih")
with colc:
    onal_file = st.file_uploader("3. Şoför Önal Özel Sohbeti (.txt)", type=["txt"], key="src_onal")

all_dataframes = []

if grup_file is not None:
    all_dataframes.append(parse_single_source(grup_file.read().decode("utf-8", errors="ignore")))
if salih_file is not None:
    all_dataframes.append(parse_single_source(salih_file.read().decode("utf-8", errors="ignore"), force_driver="Salih"))
if onal_file is not None:
    all_dataframes.append(parse_single_source(onal_file.read().decode("utf-8", errors="ignore"), force_driver="Önal"))

if all_dataframes:
    df_combined = pd.concat(all_dataframes, ignore_index=True)
    
    if not df_combined.empty:
        df_combined = df_combined.sort_values(by=["Şoför", "dt_object"]).reset_index(drop=True)
        
        filtered_rows = []
        son_sefer_zamani = {"Önal": None, "Salih": None, "Hasib": None}
        
        for idx, row in df_combined.iterrows():
            d_name = row["Şoför"]
            dt_curr = row["dt_object"]
            
            if son_sefer_zamani[d_name] is not None:
                diff_minutes = (dt_curr - son_sefer_zamani[d_name]).total_seconds() / 60
                if diff_minutes < 60:
                    continue
                    
            son_sefer_zamani[d_name] = dt_curr
            filtered_rows.append(row)
            
        df = pd.DataFrame(filtered_rows)
        
        # --- 🚀 SAL KASA / ARKA ARKAYA SEFERLER ARASI MESAFE KONTROL MOTORU 🚀 ---
        df = df.sort_values(by=["Şoför", "dt_object"]).reset_index(drop=True)
        
        sal_kasa_mesafeleri = []
        sal_kasa_yakitlari = []
        sal_kasa_aciklamalari = []
        
        for idx, row in df.iterrows():
            if idx == 0:
                sal_kasa_mesafeleri.append(0.0)
                sal_kasa_yakitlari.append(0.0)
                sal_kasa_aciklamalari.append("Dönem Başlangıcı")
                continue
            
            prev_row = df.iloc[idx - 1]
            
            # Eğer bir önceki kayıt aynı şoföre aitse ve her iki iş de LİMAN varışlı ise (Depodan Limana)
            # Bu durum şoförün limana yük bıraktıktan sonra yeni yük için depoya boş dorse / sal kasa gittiğini kanıtlar
            if row["Şoför"] == prev_row["Şoför"]:
                # Liman teslimatından sonra, yeni işin deposuna geri dönüş boş KM maliyeti hesaplanır
                geri_donus_km = DEPO_MESAFELERI.get(row["Depo_Kodu"], 8.0)
                # Boş sal kasa gitme yakıtı hesaplanır (Yük durumu=False)
                sal_kasa_litre = calculate_real_consumption(geri_donus_km, False, row["dt_object"])
                
                sal_kasa_mesafeleri.append(geri_donus_km)
sal_kasa_yakitlari.append(round(sal_kasa_litre, 2))
sal_kasa_aciklamalari.append(f"Liman'dan {row['Depo_Kodu'].upper()} Deposuna Konteynırsız Boş Dönüş")
else:
sal_kasa_mesafeleri.append(0.0)
sal_kasa_yakitlari.append(0.0)
sal_kasa_aciklamalari.append("Şoför Değişimi veya İlk Sefer")
df["Sal Kasa Boş KM"] = sal_kasa_mesafeleri
df["Sal Kasa Boş Yakıt (Litre)"] = sal_kasa_yakitlari
df["Sefer Detay Notu"] = sal_kasa_aciklamalari
# Toplam Tüketim Değerlerini Güncelle (Sefer İçi + Sefer Arası Boş Dönüş Yakıtı)
df["Hesaplanan Tüketim (Litre)"] = df["Hesaplanan Tüketim (Litre)"] + df["Sal Kasa Boş Yakıt (Litre)"]
st.success(f"✅ Teyit Senkronizasyonu Başarılı! 3 kanaldan gelen veriler filtrelendi ve {len(df)} adet net benzersiz sefer listelendi.")
df["dt_object"] = pd.to_datetime(df["dt_object"])
min_date = df["dt_object"].min()
max_date = df["dt_object"].max()
gun_sayisi = (max_date - min_date).days
if gun_sayisi < 1:
gun_sayisi = 1
donemlik_sabit_gider_payi = TOPLAM_SIRKET_GUNLUK_GIDERI * gun_sayisi
total_ciro = df["Sefer Cirosu (TL)"].sum()
total_prim = df["Şoför Primi (TL)"].sum()
gercek_tuketilen_yakit = manuel_alinan_litre - depodaki_mevcut_litre
gercek_yakit_maliyeti = gercek_tuketilen_yakit * manuel_litre_fiyati
net_sirket_kari = total_ciro - total_prim - gercek_yakit_maliyeti - donemlik_sabit_gider_payi
col1, col2, col3, col4 = st.columns(4)
col1.metric("Toplam Brüt Ciro (KDV Dahil)", f"{total_ciro:,.2f} TL")
col2.metric("Toplam Şoför Primleri", f"{total_prim:,.2f} TL")
col3.metric("Gerçek Yakıt Maliyeti", f"{gercek_yakit_maliyeti:,.2f} TL", f"{gercek_tuketilen_yakit:,.1f} L Sarfiyat")
col4.metric("Şirket Net Kârı", f"{net_sirket_kari:,.2f} TL", f"{gun_sayisi} Günlük Gider Dağıtıldı (-{donemlik_sabit_gider_payi:,.2f} TL)")
tab1, tab2, tab3 = st.tabs(["💵 Haftalık Şoför Primleri", "🎯 Güzergah Kârlılık Karnesi", "📋 Sefer Sefer Detay Listesi"])
with tab1:
df_weekly_pivot = df.pivot_table(index="Lojistik Haftası", columns="Şoför", values="Şoför Primi (TL)", aggfunc="sum").fillna(0)
st.dataframe(df_weekly_pivot, use_container_width=True)
with tab2:
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
st.dataframe(df_group[["Güzergah Hat Değeri", "Sefer_Sayisi", "Toplam_Ciro", "Net Bırakılan Kâr (TL)", "Sefer Başı Ortalama Kâr (TL)"]], use_container_width=True)
with tab3:
st.dataframe(df[["Şoför", "Tarih / Saat", "Güzergah Hat Değeri", "Sal Kasa Boş KM", "Sal Kasa Boş Yakıt (Litre)", "Hesaplanan Tüketim (Litre)", "Sefer Detay Notu", "Sefer Cirosu (TL)"]], use_container_width=True, height=500)
else:
st.error("Yüklenen dosyalarda geçerli bir nakliye güzergahı bulunamadı.")
