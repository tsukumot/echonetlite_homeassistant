[ECHONETLite Platform Custom Component for Home Assistant](https://github.com/scottyphillips/echonetlite_homeassistant)を快適エアリーに対応させようとしています。
まだ全然途中です。

現段階では主な値が取れるだけで、設定変更はあまりできません。

## 使い方
[custom_components/echonetlite/quirks/Chofu Seisakusho/MC-38/0130.py](https://raw.githubusercontent.com/tsukumot/echonetlite_homeassistant/refs/heads/master/custom_components/echonetlite/quirks/Chofu%20Seisakusho/MC-38/0130.py)

このファイルを同じディレクトリ構造で入れるだけでも、気温や湿度などの値を取得するエンティティが生成されます。とりあえずセンサーとして使いたい場合にどうぞ。

もし、機器名（MC-38）が異なる場合はディレクトリ名を変更してください。
ただし動作保証などはできません。（ほかの環境でテストできないため）

### 設定値を変更するために追加/編集が必要なファイル
絶賛開発中。
- connectors.py
- climate.py
- climate_KAITEKI.py

## 進行状況
- 各値の読み出し、エンティティ化
- 0xF2の設定値を見て、ゾーンの分け方を判定
- 1〜3つのゾーンごとにClimateエンティティを生成（途中）
- Climateエンティティから設定値の変更はできない

## Thanks
制作に当たり、[ECHONETLite Custom MRA](https://github.com/hiroaki0923/ECHONETLite-Custom-MRA)を参考にさせていただきました。

多謝。 
