# CipherSpectrum STTabNet v1~v3 실험 기록

## 목표

CipherSpectrum PCAP에서 암호군 정보와 SNI를 모델 입력으로 쓰지 않고, 패킷 크기·방향·시간 패턴만으로 도메인 40개를 다중 분류한다.

데이터의 최상위 폴더는 아래 형식이다.

```text
none_aes128gcm_google.com
none_aes256gcm_google.com
none_chacha20poly1305_google.com
```

학습 레이블은 cipher prefix를 제거한 도메인명이다.

```text
google.com
naver.com
...
```

`getpocket.com`과 `chacha20`은 세 cipher에 공통으로 존재하지 않아 제외했다.

```text
추출 flow: 123,000
학습 flow: 120,000
클래스: 40 domain
제외 flow: 3,000
```

## 공통 전처리

`extract_pcap_seq_sni_v2.py`가 PCAP을 TCP/UDP 양방향 flow로 나누고, flow당 처음 100개 패킷을 저장한다.

```text
packet_size
direction
iat_ms
tcp_window
retrans
payload_size
mask
```

`mask`는 100개보다 짧은 flow의 zero-padding 위치를 구분한다.

모든 버전에서 SNI·IP·원본 폴더명은 모델 입력 피처에서 제외했다. SNI는 도메인을 직접 노출할 수 있어 traffic fingerprinting 실험에서는 누수다.

## 모델 구조

```text
시퀀스 stream
  패킷 시퀀스 → Conv1d patch embedding → positional embedding
  → Transformer encoder → pooling

표형 stream
  flow 통계 → NonlinearTabularEncoder

fusion
  두 stream 결합 → gate → classifier → domain logits
```

`NonlinearTabularEncoder`는 `Linear(x) + Linear(sin(x))` 기반이다. 이름에 KAN 아이디어가 있었지만, 엄밀한 spline-KAN 구현은 아니다.

## v1: 초기 baseline

학습 파일: `01_code/train_cipherspectrum_sttabnet.py`

### 입력과 구조

```text
시퀀스 채널: 2
  - signed packet size
  - log1p(IAT)

Transformer: 2 layers, seq_dim=32
Tabular dimension: 64
Conv patch stride: 2
```

### 분할과 한계

```text
Train/Test: 96,000 / 24,000
PCAP 단위 그룹 분할
```

매 epoch에서 test fold를 평가하고 최고 모델을 고르는 방식이었다. 따라서 test set이 model selection에 사용되어 엄밀한 최종 성능 평가는 아니다.

또한 padding mask를 Transformer attention과 pooling에서 쓰지 않았다. 짧은 flow의 0-padding이 시퀀스 표현에 섞일 수 있었다.

### 결과

```text
Accuracy: 83.29%
Macro F1: 83.08%
Weighted F1: 83.08%
Epoch: 30
RAM peak: 1,861 MiB
GPU reserved: 106 MiB
```

## v2: mask·피처·평가 개선

학습 파일: `01_code/train_cipherspectrum_sttabnet_v2.py`

### 개선

1. Padding mask 적용

```text
Transformer src_key_padding_mask 적용
실제 patch만 평균 pooling
```

2. Residual gate

```python
fused_features = features * (1.0 + gate(features))
```

기존의 `features * gate(features)`는 중요한 특징도 0에 가깝게 줄일 수 있었다.

3. 시퀀스 채널 확장

```text
signed packet size
log1p(IAT)
signed payload size
log1p(TCP window)
retransmission
```

4. 정석 train/validation/test 분리

```text
Train: 76,800
Validation: 19,200
Test: 24,000
```

outer fold는 final test, inner fold는 validation이다. 두 분할 모두 PCAP 단위 그룹 분할이다.

5. 학습 안정화

```text
AdamW
ReduceLROnPlateau
validation Macro F1 기준 best checkpoint
early stopping patience=10
```

### 결과

```text
Test Accuracy: 91.62%
Test Macro F1: 91.54%
Test Weighted F1: 91.54%
Best validation Macro F1: 91.18%
Iterations: 18,000
RAM peak: 2,302 MiB
GPU reserved: 216 MiB
```

v1 대비 Macro F1은 `+8.46%p` 상승했다. 다만 v1은 test fold로 model selection을 했으므로 절대 비교에는 평가 방식 차이가 포함된다.

## v3: sequence capacity 확장

학습 파일: `01_code/train_cipherspectrum_sttabnet_v2.py`에 확장 옵션 적용.

### 개선

```text
시퀀스 채널: 5 → 6
추가 채널: direction

patch stride: 2 → 1
Transformer: 2 → 3 layers
seq_dim: 64 → 96
tab_dim: 96 → 128
attention pooling 사용
```

Stride 1은 100개 패킷을 50개 patch 대신 약 100개 patch로 유지한다. Attention pooling은 모든 packet patch를 동일 평균하지 않고, domain 구분에 중요한 patch에 큰 가중치를 준다.

### 결과

```text
Test Accuracy: 91.91%
Test Macro F1: 91.88%
Test Weighted F1: 91.88%
Best validation Macro F1: 92.15%
Best epoch: 59
Iterations: 18,000
RAM peak: 2,403 MiB
GPU reserved: 740 MiB
```

### v2 대비

```text
Macro F1: 91.54% → 91.88%  (+0.34%p)
Epoch time: 약 6초 → 약 17초
GPU reserved: 216 MiB → 740 MiB
```

v3는 성능 개선은 작고 연산 비용은 크다. 현재 기준 기본 모델은 v2가 효율적이며, 최고 단일 fold 성능이 필요할 때 v3를 사용한다.

## 현재 한계

1. 동일 데이터셋 내부 평가다.

```text
같은 CipherSpectrum 수집 환경
같은 도메인 집합
같은 PCAP 생성 방식
```

새 브라우저·날짜·네트워크·MTU·RTT·패킷 손실 환경에서는 성능이 낮아질 수 있다.

2. 현재 결과는 fold 0 하나다.

```text
fold 0~4 Macro F1 평균 ± 표준편차 필요
```

3. 어려운 클래스가 남아 있다.

v2 기준 낮은 클래스는 `gmx.net`, `yimg.jp`, `yahoo.co.jp`, `web.de`였다. confusion matrix로 오분류 상대를 확인해야 한다.

4. flow 길이 상한은 100 packet이다.

전체 flow의 중앙값은 26 packet, 90 percentile은 109 packet이다. 100 packet은 대부분을 포함하지만 긴 flow 일부 정보는 버린다.

## 다음 권장 실험

```text
1. v2/v3 fold 0~4 실행, 평균 ± 표준편차 보고
2. confusion matrix 저장·저성능 domain 분석
3. 다른 네트워크/날짜/브라우저 데이터셋 external test
4. 필요 시 max-packets=200 재추출 후 비교
5. VPN-2016, Tor-2016에서 범용 다중분류기 평가
```

## 재현 명령

### v2

```bash
APP_DIR=/root/02_SGS/lab_dashboard_ver0.1

python3 "$APP_DIR/01_code/train_cipherspectrum_sttabnet_v2.py" \
  --sequence-dir "$APP_DIR/02_dataset/cipherspectrum_seq_100_v1" \
  --output-dir "$APP_DIR/cipherspectrum_sttabnet_v2_fold0" \
  --epochs 60 --batch-size 256 --workers 4 --device auto \
  --imbalance none
```

### v3

```bash
APP_DIR=/root/02_SGS/lab_dashboard_ver0.1

python3 "$APP_DIR/01_code/train_cipherspectrum_sttabnet_v2.py" \
  --sequence-dir "$APP_DIR/02_dataset/cipherspectrum_seq_100_v1" \
  --output-dir "$APP_DIR/cipherspectrum_sttabnet_v3_fold0" \
  --epochs 60 --batch-size 256 --workers 4 --device auto \
  --imbalance none \
  --seq-dim 96 --tab-dim 128 \
  --patch-stride 1 --transformer-layers 3 --attention-pool
```
