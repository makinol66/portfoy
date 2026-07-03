import yfinance as yf
import pandas as pd
import numpy as np

def test_et():
    print("="*50)
    print("🎯 ORİJİNAL TEMEL ANALİZ KODUYLA PD/DD TESTİ")
    print("="*50)
    
    hisse = input("Lütfen analiz edilecek hisse kodunu girin (Örn: TUPRS): ").upper().strip()
    
    if not hisse:
        print("Boş giriş yapıldı. Çıkılıyor...")
        return
        
    yf_kodu = f"{hisse}.IS" if not hisse.endswith(".IS") else hisse
    tk = yf.Ticker(yf_kodu)
    
    pddd_5y_ort = None
    
    print(f"\n⏳ {yf_kodu} için Yahoo Finance'tan Bilanço ve Fiyat geçmişi çekiliyor...")
    
    try:
        bs = tk.balance_sheet
        if not bs.empty:
            print("✅ Bilanço verisi alındı.")
            bs_idx_lower = [str(i).lower() for i in bs.index]
            eq_idx = next((i for i, name in enumerate(bs_idx_lower) if "stockholders equity" in name or "total equity" in name), None)
            sh_idx = next((i for i, name in enumerate(bs_idx_lower) if "ordinary shares" in name or "share capital" in name), None)
            
            if eq_idx is not None and sh_idx is not None:
                print("✅ Özkaynak ve Sermaye satırları tespit edildi.")
                eq_row = bs.iloc[eq_idx]
                sh_row = bs.iloc[sh_idx]
                
                # Sizin orijinal kodunuzdaki fiyat çekme fonksiyonu
                hist_prices = tk.history(period="5y", interval="1mo")
                print("✅ 5 Yıllık fiyat geçmişi alındı.")
                
                pddd_degerleri = []
                for col_date in bs.columns:
                    try:
                        ozkaynak = eq_row[col_date]
                        hisse_sayisi = sh_row[col_date]
                        if pd.isna(ozkaynak) or pd.isna(hisse_sayisi) or hisse_sayisi == 0:
                            continue
                        hb_defter = float(ozkaynak) / float(hisse_sayisi)
                        
                        if hist_prices.index.tz is not None:
                            target_dt = pd.to_datetime(col_date).tz_localize(hist_prices.index.tz)
                        else:
                            target_dt = pd.to_datetime(col_date).tz_localize(None)
                            
                        en_yakin_idx = hist_prices.index.get_indexer([target_dt], method='nearest')[0]
                        fiyat = float(hist_prices.iloc[en_yakin_idx]['Close'])
                        
                        if hb_defter > 0 and fiyat > 0:
                            pddd_degerleri.append(fiyat / hb_defter)
                            print(f"  🟢 Tarih: {col_date.date()} | PD/DD: {fiyat / hb_defter:.2f}")
                    except Exception as ex:
                        print(f"  ⚠️ {col_date.date()} tarihinde eşleştirme hatası: {ex}")
                        continue
                        
                if pddd_degerleri:
                    pddd_5y_ort = float(np.mean(pddd_degerleri))
                    print(f"\n🎉 SONUÇ: {yf_kodu} İçin 5 Yıllık PD/DD Ortalaması = {pddd_5y_ort:.2f}")
            else:
                print("❌ HATA: Bilançoda Özkaynak veya Hisse Sayısı satırı bulunamadı!")
        else:
            print("❌ HATA: Yahoo Finance bilanço tablosunu boş (empty) döndürdü. (API Rate Limit)")
    except Exception as e:
        print(f"❌ GENEL HATA: {e}")

if __name__ == "__main__":
    test_et()