[ECHONETLite Platform Custom Component for Home Assistant](https://github.com/scottyphillips/echonetlite_homeassistant)を快適エアリーに対応させようとしています。

基本的な機能は粗方扱えるようになりました。
タイマー関係はまだです。

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
- select_KAITEKI.py
- switch.py
- translations/ja.json

## やったこと
- 各値の読み出し、エンティティ化
- 0xF2の設定値を見て、ゾーンの分け方を判定
  - ほぼ確実に機種依存であるため、climate_KAITEKI.pyのKAITEKI_PRODUCT_CODESに機種名を追加する方式
- 1〜3つのゾーンごとにClimateエンティティを生成
  - Climateの運転モードには現在の運転モード（要するにON）とオフのみ選択可能
  - 短時間で入力された設定変更（主にオートメーションによるもの）はまとめて送信
  - OFF/Keepの挙動はコントローラーと同様
    - そもそも、Keepを選択するかどうかを決めるのはエアリー側で、送信側では指定できない
    - つまり、ZoneStatusに送信できるのはON/OFFのみ
- 主電源のためにSwitch、運転モード選択のためにSelectをそれぞれ生成
  - および、そのための分岐点追加
  - いずれも変更時に全てのZoneの運転がONになるのは**エアリー側の仕様**
  - 気になるならオートメーションなどから対応してください
- おすすめタイマーのSelectを追加
- QUIRKSに"ALWAYS_POLL"のオプションを追加
  - おすすめタイマー動作による運転モード移行を検出するため


## 今後の予定
- オン/オフタイマー対応
- おすすめタイマーの内容設定


## Thanks
制作に当たり、[ECHONETLite Custom MRA](https://github.com/hiroaki0923/ECHONETLite-Custom-MRA)を参考にさせていただきました。

多謝。