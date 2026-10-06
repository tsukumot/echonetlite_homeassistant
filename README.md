[ECHONETLite Platform Custom Component for Home Assistant](https://github.com/scottyphillips/echonetlite_homeassistant)を快適エアリーに対応させようとしています。
まだ全然途中です。

現段階では主な値が取れるだけで、設定変更はあまりできません。

## 使い方
[custom_components/echonetlite/quirks/Chofu Seisakusho/MC-38/0130.py](https://raw.githubusercontent.com/tsukumot/echonetlite_homeassistant/refs/heads/master/custom_components/echonetlite/quirks/Chofu%20Seisakusho/MC-38/0130.py)

このファイルを同じディレクトリ構造で入れるだけでも、気温や湿度などの値を取得するエンティティが生成されます。

もし、機器名（MC-38）が異なる場合はディレクトリ名を変更してください。
ただ、機器のバージョンが大きく異なる場合の動作保証などはできません。（テストできないため）

## 進行状況
- 0xF2の設定値を見て、最大3つ、最小1つのゾーンごとにClimateエンティティを生成。
- 設定変更はまだ動作しない。

## Thanks
なお、制作に当たり、[ECHONETLite Custom MRA](https://github.com/hiroaki0923/ECHONETLite-Custom-MRA)を参考にさせていただきました。

多謝。 
