import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinterdnd2 import DND_FILES, TkinterDnD
import pandas as pd
import os
import re

class AutoSelectCSVMergerApp(TkinterDnD.Tk):
    def __init__(self):
        super().__init__()

        self.title("Auto Select CSV Merger")
        self.geometry("600x550")
        self.configure(bg="#f0f0f0")
        
        self.file_paths = []

        # ==========================================
        # 【ここをカスタマイズ】自動選択のキーワード設定
        # ==========================================
        # 型番（基準列）とみなすキーワードのリスト
        self.key_keywords = [
            "型番", "品番", "商品コード", "JAN", "SKU", 
            "ItemCode", "Product ID", "ID", "コード", 
            "product", "digikey"
        ]
        
        # 数量（集計列）とみなすキーワードのリスト
        self.val_keywords = [
            "数量", "数", "在庫", "発注数", "Qty", 
            "Quantity", "Amount", "Volume", "個数"
        ]
        # ==========================================

        # --- UI構築 ---

        # 1. 設定エリア（上部）
        frame_top = tk.Frame(self, bg="#f0f0f0")
        frame_top.pack(pady=15, fill='x', padx=20)

        # 集計列（値）の選択
        tk.Label(frame_top, text="集計列 (数量等):", bg="#f0f0f0").grid(row=0, column=0, sticky="w", padx=(10,0))
        self.combo_val = ttk.Combobox(frame_top, width=20, state="readonly")
        self.combo_val.grid(row=0, column=1, padx=5)

        # 基準列（キー）の選択
        tk.Label(frame_top, text="基準列 (型番等):", bg="#f0f0f0").grid(row=0, column=2, sticky="w")
        self.combo_key = ttk.Combobox(frame_top, width=20, state="readonly")
        self.combo_key.grid(row=0, column=3, padx=5)

        # 2. 説明とリストエリア
        tk.Label(self, text="CSVファイルをリストにドロップしてください。\n(キーワードに一致する列を自動選択します)", bg="#f0f0f0").pack(pady=(5, 0))

        frame_list = tk.Frame(self)
        frame_list.pack(pady=5, padx=20, fill='both', expand=True)

        self.listbox = tk.Listbox(frame_list, selectmode=tk.EXTENDED, height=10)
        self.listbox.pack(side=tk.LEFT, fill='both', expand=True)
        
        scrollbar = tk.Scrollbar(frame_list, orient="vertical", command=self.listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill='y')
        self.listbox.config(yscrollcommand=scrollbar.set)

        # D&D設定
        self.listbox.drop_target_register(DND_FILES)
        self.listbox.dnd_bind('<<Drop>>', self.drop_handler)

        # 3. ボタンエリア
        frame_btn = tk.Frame(self, bg="#f0f0f0")
        frame_btn.pack(pady=20)

        btn_clear = tk.Button(frame_btn, text="リストをクリア", command=self.clear_list, bg="#6c757d", fg="white")
        btn_clear.pack(side=tk.LEFT, padx=10)

        btn_run = tk.Button(frame_btn, text="マージして保存", command=self.run_merge, 
                            bg="#007bff", fg="white", font=("Meiryo", 12, "bold"), width=20)
        btn_run.pack(side=tk.LEFT, padx=10)
        
        self.lbl_status = tk.Label(self, text="待機中...", bg="#ddd", anchor="w")
        self.lbl_status.pack(side=tk.BOTTOM, fill='x')

    def read_csv_auto_enc(self, path):
        """文字コード自動判別読み込み"""
        try:
            return pd.read_csv(path, encoding='utf-8')
        except UnicodeDecodeError:
            try:
                return pd.read_csv(path, encoding='cp932')
            except Exception:
                return None
        except Exception:
            return None

    def drop_handler(self, event):
        """ファイルを解析してリスト追加＆ヘッダー取得"""
        data = event.data
        paths = re.findall(r'\{.*?\}|\S+', data)
        
        added_count = 0
        for path in paths:
            clean_path = path.strip('{}')
            if clean_path not in self.file_paths:
                self.file_paths.append(clean_path)
                self.listbox.insert(tk.END, os.path.basename(clean_path))
                added_count += 1
        
        # ファイルが追加されたら、最初のファイルの列情報を取得してコンボボックスを更新
        if self.file_paths:
            self.update_column_options(self.file_paths[0])

        self.lbl_status.config(text=f"{added_count} ファイル追加 (合計: {len(self.file_paths)})")

    def update_column_options(self, file_path):
        """CSVヘッダーを読み取り、キーワードにマッチするものを自動選択"""
        df = self.read_csv_auto_enc(file_path)
        if df is not None:
            columns = df.columns.tolist()
            
            # コンボボックスの選択肢を更新
            self.combo_key['values'] = columns
            self.combo_val['values'] = columns

            # --- 自動選択ロジック ---
            
            # 1. 基準列（型番など）を探す
            selected_key = ""
            # 現在の選択がまだ有効なら維持、無ければ探す
            current_key = self.combo_key.get()
            if current_key not in columns:
                for col in columns:
                    # キーワードリストのどれかが列名に含まれているかチェック
                    if any(kw in col for kw in self.key_keywords):
                        selected_key = col
                        break # 見つかったら終了（左側の列優先）
                
                # キーワードで見つかればセット、なければ先頭
                if selected_key:
                    self.combo_key.set(selected_key)
                elif columns:
                    self.combo_key.current(0)

            # 2. 集計列（数量など）を探す
            selected_val = ""
            current_val = self.combo_val.get()
            if current_val not in columns:
                for col in columns:
                    # 基準列と同じものは選ばないようにする
                    if col == self.combo_key.get():
                        continue

                    if any(kw in col for kw in self.val_keywords):
                        selected_val = col
                        break
                
                # キーワードで見つかればセット、なければ2番目（なければ先頭）
                if selected_val:
                    self.combo_val.set(selected_val)
                elif len(columns) > 1:
                    # 基準列と被らないように2番目を選ぶなどの配慮
                    idx = 1 if self.combo_key.current() == 0 else 0
                    self.combo_val.current(idx)
                elif columns:
                    self.combo_val.current(0)

    def clear_list(self):
        self.file_paths = []
        self.listbox.delete(0, tk.END)
        self.combo_key.set('')
        self.combo_val.set('')
        self.combo_key['values'] = []
        self.combo_val['values'] = []
        self.lbl_status.config(text="リストをクリアしました")

    def run_merge(self):
        if not self.file_paths:
            messagebox.showwarning("警告", "CSVファイルを追加してください。")
            return

        key_col = self.combo_key.get()
        val_col = self.combo_val.get()

        if not key_col or not val_col:
            messagebox.showwarning("警告", "基準列と集計列を選択してください。")
            return

        try:
            self.lbl_status.config(text="処理中...")
            self.update()

            df_list = []
            for path in self.file_paths:
                df = self.read_csv_auto_enc(path)
                if df is None:
                    raise ValueError(f"ファイル読み込みエラー: {os.path.basename(path)}")
                
                if key_col not in df.columns or val_col not in df.columns:
                    raise ValueError(f"ファイル「{os.path.basename(path)}」に\n指定された列が見つかりません。")
                
                df_list.append(df)

            # 結合
            df_concat = pd.concat(df_list, ignore_index=True)
            
            # 集計
            df_merged = df_concat.groupby(key_col, as_index=False)[val_col].sum()

            save_path = filedialog.asksaveasfilename(
                defaultextension=".csv",
                filetypes=[("CSV Files", "*.csv")],
                title="保存先を選択",
                initialfile="merged_result.csv"
            )

            if save_path:
                df_merged.to_csv(save_path, index=False, encoding='utf-8-sig')
                self.lbl_status.config(text="完了しました")
                messagebox.showinfo("成功", f"マージ完了！\n合計 {len(df_merged)} 行のデータを作成しました。")
            else:
                self.lbl_status.config(text="キャンセルされました")

        except Exception as e:
            self.lbl_status.config(text="エラー発生")
            messagebox.showerror("エラー", str(e))

if __name__ == "__main__":
    app = AutoSelectCSVMergerApp()
    app.mainloop()