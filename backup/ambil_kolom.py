import pandas as pd

def dapatkan_header_baris_dua(url):
    try:
        csv_url = url.split('/edit')[0] + '/export?format=csv&' + url.split('?')[1].split('#')[0]
        
        print("Mengambil data dari Sheet 'MIRORING MICRODEMAND'...\n")
        
        df = pd.read_csv(csv_url, header=1)
        headers = df.columns.tolist()
        
        for i in range(36):
            if i < len(headers):
                if "Unnamed" in str(headers[i]):
                     header_value = "(Kosong)"
                else:
                     header_value = headers[i]
            else:
                header_value = "(Kosong)"
                
            if i < 26:
                col_letter = chr(65 + i)
            else:
                col_letter = 'A' + chr(65 + (i - 26))
                
            print(f"{header_value} = Kolom {col_letter} (index {i})")

    except Exception as e:
        print(f"Terjadi kesalahan saat menjalankan kode: {e}")

url_gsheet = "https://docs.google.com/spreadsheets/d/14-kuUd115VsqmrR88MKqe3jtq_zdlYarB7HvNIDa4fE/edit?gid=1333336932#gid=1333336932"
dapatkan_header_baris_dua(url_gsheet)