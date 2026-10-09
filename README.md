[ECHONETLite Platform Custom Component for Home Assistant](https://github.com/scottyphillips/echonetlite_homeassistant)を快適エアリーに対応させようとしています。
まだ途中です。

現段階では主な値が取れるだけで、設定変更はあまりできません。

## 使い方
[custom_components/echonetlite/quirks/Chofu Seisakusho/MC-38/0130.py](https://raw.githubusercontent.com/tsukumot/echonetlite_homeassistant/refs/heads/master/custom_components/echonetlite/quirks/Chofu%20Seisakusho/MC-38/0130.py)

このファイルを同じディレクトリ構造で入れるだけでも、気温や湿度などの値を取得するエンティティが生成されます。とりあえずセンサーとして使いたい場合にどうぞ。

もし、機器名（MC-38）が異なる場合はディレクトリ名を変更してください。
ただし動作保証などはできません。（ほかの環境でテストできないため）

### 機器の設定値を変更するために追加/編集したファイル
- connectors.py
- climate.py
- climate_KAITEKI.py
- select.py
- switch.py
- translations/ja.json

## 進行状況
- 各値の読み出し、エンティティ化
- 0xF2の設定値を見て、ゾーンの分け方を判定
- 1〜3つのゾーンごとにClimateエンティティを生成
  - Climateの運転モードには現在の運転モード（要するにON）とオフのみ選択可能
  - OFF/Keepの挙動はコントローラーと同様
    - 正確には、OFFを送った際に条件が揃うとエアリー側で分岐してKeepを選択するので、それに表示を合わせた
- 主電源はSwitch、運転モード選択についてはSelectをそれぞれ生成
  - いずれも変更時に全てのZoneの運転がONになるのは**エアリー側の仕様**
  - 気になるならオートメーションなどから対応してください


## 予定メモ
- 0xF2は機器依存であることがほぼ確実なため、分岐を作る
- おすすめタイマーの選択
- オン/オフタイマーに対応
- 不要なエンティティの整理


## Thanks
制作に当たり、[ECHONETLite Custom MRA](https://github.com/hiroaki0923/ECHONETLite-Custom-MRA)を参考にさせていただきました。

多謝。 
