from pathlib import Path
import io
import re
from typing import List, Dict, Any, Tuple, Optional, Set

def parse_sym_lib_table(text: str) -> Tuple[Optional[Any], List[Dict[str, str]]]:
		
	version: Optional[Any] = 7
	version_match = re.search(r'\(\s*version\s+([^\)]+)\)', text)
	
	if version_match:
		version_str = version_match.group(1).strip()
		try:
			version = int(version_str)
		except ValueError:
			version = 7
					
	lib_content_matches = re.finditer(
		r'\(\s*lib\s+'                  # (lib で始まる
        r'('                             # グループ1開始 (libの中身)
          r'(?:\s*'                       # 
            r'\(\s*(\w+)\s+'              # (key (グループ2: キー)
            r'"((?:\\"|[^"])*)"'        # "value" (グループ3: 値)
            r'\s*\)'                      # )
          r'\s*)+'                       # 上記 (key "value") の1回以上の繰り返し
        r')'                             # グループ1終了
        r'\s*\)',                         # 閉じる )
		text
	)
	libs: List[Dict[str, str]] = []
	
	# 3. 各libブロックの中身を辞書にパース
	for match in lib_content_matches:
		# libブロックの中身の文字列 ( (name ...)(type ...)... )
		content_str = match.group(1)
		lib_info: Dict[str, str] = {}
		
		# (key "value") のペアをすべて見つける
		value_matches = re.findall(
			r'\(\s*(\w+)\s+"((?:\\"|[^"])*)"\s*\)', 
			content_str
		)
		
		for key, value in value_matches:
			if key in ["name", "type", "uri", "options", "descr"]:
				lib_info[key] = value.replace(r'\"', '"')
		
		if 'name' in lib_info:
			libs.append(lib_info)
					
	return version, libs



def file_open(path) -> Tuple[io.TextIOWrapper,str] | None:
	file = Path(path)

	try:
		f = file.open(mode='r+', encoding='utf-8')
		data = f.read()
		f.seek(0)
		f.truncate()
		return (f,data)
	except FileNotFoundError:
		try:
			f = file.open(mode='w', encoding='utf-8')
			return (f,"")
		except IOError as e:
			print(f"ファイルの作成に失敗しました: {e}")	
			return None
	except IOError as e:
		print(f"ファイルの読み込みに失敗しました: {e}")
		return None







FOOTPL_PROP = "fp-lib-table"
SYMBOL_PROP = "sym-lib-table"
DESIGN_PROP = "design-block-lib-table"

MODELS_DIR = "./library/models"
FOOTPL_DIR = "./library/footprints"
SYMBOL_DIR = "./library/symbols"
DESIGN_DIR = "./library/designs"

##### ライブラリフォルダの生成
model_dir        = Path(MODELS_DIR)
symbol_dir       = Path(SYMBOL_DIR)
footprint_dir    = Path(FOOTPL_DIR)
design_block_dir = Path(DESIGN_DIR)

try:
	model_dir.mkdir       (parents=True, exist_ok=True)
	symbol_dir.mkdir      (parents=True, exist_ok=True)
	footprint_dir.mkdir   (parents=True, exist_ok=True)
	design_block_dir.mkdir(parents=True, exist_ok=True)
except OSError as e:
	print(f"フォルダーの作成に失敗しました: {e}")


file_list = [FOOTPL_PROP,SYMBOL_PROP,DESIGN_PROP]
file_depend = {FOOTPL_PROP:footprint_dir,SYMBOL_PROP:symbol_dir,DESIGN_PROP:design_block_dir}

for e in file_list:
	(file,s) = file_open(e)
	with file  as f:
		(version,libs) = parse_sym_lib_table(s) #パース

		suffixes = (".kicad_sym", ".pretty")
		target_dir = Path(file_depend[e])

		#ライブラリファイルの読み込み
		existing_names: Set[str] = set(lib.get("name") for lib in libs if lib.get("name"))
		try:
			for item in target_dir.iterdir():
				if item.name.endswith(suffixes) and item.stem not in existing_names:
					lib_info: Dict[str, str] = {}
					lib_info["name"] = item.stem
					lib_info["type"] = 'KiCad'
					lib_info["uri"]     = '${KIPRJMOD}/'+str(file_depend[e])+'/'+item.name
					lib_info["options"] =''
					lib_info["descr"]   = ''
					libs.append(lib_info)
		except e:
			print("ファイルの取得に失敗しました: {e}")

		#テーブルへの書き込み
		f.write('('+e.replace('-','_')+'\n')#header
		f.write('\t(version ' + str(version) + ')\n')#virsion
		for l in libs:
			f.write('\t(lib ')#head
			for key in ["name", "type", "uri", "options", "descr"]:
				f.write('('+key+' \"'+ l[key] +'\")')
			f.write(')\n')#end
		f.write(')\n')#end
		
