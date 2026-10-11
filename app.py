import datetime
import pandas as pd
import streamlit as st

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

def calculate_real_consumption(distance, is_loaded, dt):
    rate = 0.57 if is_loaded else 0.38
    traffic = 1.45 if 8 <= dt.hour <= 18 else 1.00
    return distance * rate * traffic

def is_normal_hour(dt):
    if dt.weekday() <= 4:
        return datetime.time(8, 0) <= dt.time() <= datetime.time(18, 0)
    elif dt.weekday() == 5:
        return datetime.time(8, 0) <= dt.time() <= datetime.time(13, 0)
    return False

def parse_single_source(text_content, force_driver=None):
    seferler = []
    satirlar = text_content.replace("\x00", "").replace("\ufeff", "").split("\n")
    son_depo, son_yuk = "gts", "dolu"
    son_zaman = {"Önal": None, "Salih": None, "Hasib": None}

    for satir in satirlar:
        satir = satir.strip()
        if not satir or " - " not in satir or ":" not in satir or "soda" in satir.lower():
            continue
        for k in DEPO_MESAFELERI.keys():
            if k in satir.lower():
                son_depo = k
                break
        if "boş" in satir.lower(): 
            son_yuk = "boş"
        elif "dolu" in satir.lower() or "dolusu" in satir.lower(): 
            son_yuk = "dolu"

        if not any(x in satir.lower() for x in ["<medya", "görsel", "teslim", "edildi", "ettim"]):
            continue
        try:
            t_part, r_part = satir.split(" - ", 1)
            s_part, _ = r_part.split(":", 1)
            dt = datetime.datetime.strptime(t_part.replace("[", "").replace("]", "").strip(), "%d.%m.%Y %H:%M")
        except:
            continue

        dr = force_driver if force_driver else ("Önal" if "önal" in s_part.lower() or "ünal" in s_part.lower() else "Salih" if "salih" in s_part.lower() else "Hasib" if "hasib" in s_part.lower() else None)
        if not dr: continue

        if son_zaman[dr] and (dt - son_zaman[dr]).total_seconds() / 60 < 60:
            continue
        son_zaman[dr] = dt

        f_key = f"{son_depo}_{son_yuk}"
        if "kahraman" in satir.lower() and "boş" in satir.lower(): f_key = "kahramanli_ardep_boş"
        elif "ardep" in satir.lower() and "gts" in satir.lower() and "emanet" in satir.lower(): f_key = "ardep_gts_emanet_dolu"
        elif "ardep" in satir.lower() and "emanet" in satir.lower(): f_key = "ardep_emanet_dolu"
        elif "oyak" in satir.lower(): f_key = "oyak_depo_dolusu"

        matrah = DEPO_FIYATLARI.get(f_key, 2500.0)
        km = DEPO_MESAFELERI.get(son_depo, 8.0)
        liters = calculate_real_consumption(km, (son_yuk == "dolu"), dt)

        seferler.append({
            "Şoför": dr, "dt_obj": dt, "Tarih / Saat": dt.strftime("%d/%m/%Y %H:%M"),
            "Hafta": f"{(dt - datetime.timedelta(days=dt.weekday())).strftime('%d/%m')} Haftası",
            "Güzergah": f_key.upper().replace("_", " "), "KM": km, "Litre": liters,
            "Prim": 250.0 if is_normal_hour(dt) else 500.0, "Ciro": matrah * (1 + KDV_ORANI), "Depo_Kodu": son_depo
        })
    return pd.DataFrame(seferler)

st.set_page_config(page_title="Mersin Lojistik", layout="wide")
st.title("📊 Mersin Şehiriçi Konteynır Karlılık Analiz Motoru")

st.sidebar.header("⛽ Girişler")
litre_fiyat = st.sidebar.number_input("Mazot Litre Fiyatı (TL)", value=86.50)
alinan_litre = st.sidebar.number_input("Alınan Mazot (Litre)", value=979.0)
kalan_litre = st.sidebar.number_input("Depoda Kalan Mazot (Litre)", value=250.0)
aktif_tırs = st.sidebar.number_input("Aktif Tır Sayısı", min_value=1, value=2)

gün_gideri = (((82000 + 200000) / 365) + (54000 / 30)) * aktif_tırs
st.sidebar.write(f"Günlük Toplam Sabit Gider: **{gün_gideri:,.2f} TL**")

col_a, col_b, col_c = st.columns(3)
with col_a: grup_f = st.file_uploader("1. Grup Dökümü (.txt)", type=["txt"])
with col_b: salih_f = st.file_uploader("2. Salih Özel (.txt)", type=["txt"])
with col_c: onal_f = st.file_uploader("3. Önal Özel (.txt)", type=["txt"])

dfs = []
if grup_f: dfs.append(parse_single_source(grup_f.read().decode("utf-8", errors="ignore")))
if salih_f: dfs.append(parse_single_source(salih_f.read().decode("utf-8", errors="ignore"), "Salih"))
if onal_f: dfs.append(parse_single_source(onal_f.read().decode("utf-8", errors="ignore"), "Önal"))

if dfs:
    df = pd.concat(dfs, ignore_index=True).sort_values("dt_obj").drop_duplicates(subset=["Şoför", "Tarih / Saat"]).reset_index(drop=True)
    if not df.empty:
        bk_km, bk_l, bk_note = [0.0], [0.0], ["Başlangıç"]
        for i in range(1, len(df)):
            r, p = df.iloc[i], df.iloc[i - 1]
            if r["Şoför"] == p["Şoför"]:
                k = DEPO_MESAFELERI.get(r["Depo_Kodu"], 8.0)
                bk_km.append(k)
                bk_l.append(round(calculate_real_consumption(k, False, r["dt_obj"]), 2))
                bk_note.append(f"Liman'dan {r['Depo_Kodu'].upper()} Deposuna Sal Kasa Boş Dönüş")
            else:
                bk_km.append(0.0); bk_l.append(0.0); bk_note.append("Şoför Değişimi")
        df["Boş_KM"], df["Boş_Litre"], df["Not"] = bk_km, bk_l, bk_note
        df["Litre"] = df["Litre"] + df["Boş_Litre"]

        günler = max(1, (df["dt_obj"].max() - df["dt_obj"].min()).days)
        gider_payi = gün_gideri * günler
        ciro, prim = df["Ciro"].sum(), df["Prim"].sum()
        yakit = (alinan_litre - kalan_litre) * litre_fiyat
        net_kar = ciro - prim - yakit - gider_payi

        c1, c2, col3, c4 = st.columns(4)
        c1.metric("Toplam Ciro (KDV Dahil)", f"{ciro:,.2f} TL")
        c2.metric("Toplam Şoför Primleri", f"{prim:,.2f} TL")
        col3.metric("Gerçek Yakıt Maliyeti", f"{yakit:,.2f} TL", f"{alinan_litre - kalan_litre} L Harcandı")
        c4.metric("Şirket Net Kârı", f"{net_kar:,.2f} TL", f"{günler} Günlük Sabit Gider Düşüldü")

        t1, t2, t3 = st.tabs(["💵 Haftalık Primler", "🎯 Güzergah Kârlılığı", "📋 Sefer Detayları"])
        with t1:
            st.dataframe(df.pivot_table(index="Hafta", columns="Şoför", values="Prim", aggfunc="sum").fillna(0), use_container_width=True)
        with t2:
            g = df.groupby("Güzergah").agg(Sefer=("Şoför", "count"), Ciro=("Ciro", "sum"), Prim=("Prim", "sum"), L=("Litre", "sum")).reset_index()
            g["Net_Kar"] = g["Ciro"] - g["Prim"] - (g["L"] * litre_fiyat)
            g["Sefer_Başı_Kar"] = g["Net_Kar"] / g["Sefer"]
            st.dataframe(g.sort_values("Sefer_Başı_Kar", ascending=False), use_container_width=True)
        with t3:
            st.dataframe(df[["Şoför", "Tarih / Saat", "Güzergah", "Boş_KM", "Boş_Litre", "Litre", "Not", "Ciro"]], use_container_width=True, height=500)
