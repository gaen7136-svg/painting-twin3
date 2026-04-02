import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy.optimize import linear_sum_assignment
import random

st.set_page_config(page_title="YULfactory: 보건 안전 통합 관제", layout="wide")

# --- [커스텀 UI 헬퍼 함수] ---
def metric_card(title, value, threshold, unit="ppm", decimal=1):
    exceeded = value > threshold
    bg_color = "#fff0f0" if exceeded else "#f0fff0"
    border_color = "#ff4d4d" if exceeded else "#4dff4d"
    text_color = "#990000" if exceeded else "#006600"
    icon = "🚨" if exceeded else "✅"
    
    html = f"""
    <div style="background-color: {bg_color}; padding: 15px; border-radius: 8px; border-left: 6px solid {border_color}; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
        <div style="font-size: 0.9em; font-weight: bold; color: {text_color}; margin-bottom: 5px;">{title}</div>
        <div style="font-size: 1.8em; font-weight: 900; color: {text_color};">{value:.{decimal}f} <span style="font-size: 0.45em; font-weight: normal;">{unit}</span></div>
        <div style="font-size: 0.8em; color: {text_color}; margin-top: 5px;">{icon} 기준: {threshold} {unit} 이하</div>
    </div>
    """
    return html

# --- [1. 데이터 초기화] ---
if 'workers' not in st.session_state:
    ids = [f'W_{i+1:02d}' for i in range(30)]
    levels = ['전문가']*5 + ['숙련공']*15 + ['신입']*10
    
    # 일반 용제 초기화 (소수점 1자리)
    TWA_toluene = round(random.uniform(0, 80.0), 1)
    TWA_Xylene = round(random.uniform(0, 150.0), 1)
    TWA_Ketone = round(random.uniform(0, 250.0), 1)
    
    # 💡 고위험 물질 Isocyanate (HDI) 초기화
    TWA_HDI = round(random.uniform(0.0, 0.01), 3)
    
    np.random.shuffle(levels)
    
    df = pd.DataFrame({
        'ID': ids, 'Level': levels,
        'Skill_Weight': [1.2 if l == '전문가' else 1.0 if l == '숙련공' else 0.7 for l in levels],
        'Condition': 1.0, 'Cum_Exp': 0.0, 'Work_Time': 0.0,
        'is_present': True, 'Status': '대기',
        'TWA_toluene': float(TWA_toluene),
        'TWA_Xylene': float(TWA_Xylene),
        'TWA_Ketone': float(TWA_Ketone),
        'TWA_HDI': float(TWA_HDI)
    })
    
    df['TWA_toluene'] = df['TWA_toluene'].astype(float)
    df['TWA_Xylene'] = df['TWA_Xylene'].astype(float)
    df['TWA_Ketone'] = df['TWA_Ketone'].astype(float)
    df['TWA_HDI'] = df['TWA_HDI'].astype(float)
    
    st.session_state.workers = df
    st.session_state.colors = {f'W_{i+1:02d}': f'hsl({i*12}, 70%, 50%)' for i in range(30)}
    st.session_state.log = ["🚀 안전 관제 시스템 가동"]

# --- [2. 사이드바: 실시간 제어] ---
with st.sidebar:
    st.header("🕹️ 실시간 제어판")
    on_duty_ids = st.session_state.workers[st.session_state.workers['Status'] == '근무']['ID'].tolist()
    target = st.selectbox("컨디션 하락 타겟", on_duty_ids if on_duty_ids else ["없음"])
    
    if st.button("⚠️ 즉시 컨디션 저하"):
        if target != "없음":
            st.session_state.workers.loc[st.session_state.workers['ID'] == target, 'Condition'] = 0.2
            st.toast(f"{target} 긴급 교체 리스트 등록")

    st.divider()
    st.subheader("🏬 30인 출근 현황")
    for i in range(30):
        w = st.session_state.workers.iloc[i]
        cb = st.checkbox(f"{w['ID']} ({w['Level']})", value=bool(w['is_present']), key=f"p_{w['ID']}")
        if cb != w['is_present']:
            st.session_state.workers.at[i, 'is_present'] = cb
            if not cb: 
                st.session_state.workers.at[i, 'Status'] = '퇴근'
            st.rerun()

# --- [3. 메인 관제 로직 (Fragment 1.5초 주기)] ---
@st.fragment(run_every=1.5)
def update_dashboard():
    workers = st.session_state.workers

    # 실시간 TWA 값 변화 모사
    twa_ranges = {
        'TWA_toluene': (0.0, 120.0),
        'TWA_Xylene': (0.0, 220.0),
        'TWA_Ketone': (0.0, 300.0),
        'TWA_HDI': (0.0, 0.015)   # HDI 가동 범위
    }
    
    for col, (low, high) in twa_ranges.items():
        current = float(workers[col].iloc[0])
        
        # HDI 물질 특성에 맞춰 변동폭(delta)과 소수점 자리를 다르게 적용
        if col == 'TWA_HDI':
            delta = np.random.uniform(-0.002, 0.002)
            new_value = round(np.clip(current + delta, low, high), 3)
        else:
            delta = np.random.uniform(-3.0, 3.0)
            new_value = round(np.clip(current + delta, low, high), 1)
            
        st.session_state.workers[col] = float(new_value)

    # A. 인력 교체 로직
    LIMIT_EXPOSURE = 70.0 
    
    to_exit = workers[(workers['Status'] == '근무') & 
                      ((workers['Work_Time'] >= 8.0) | 
                       (workers['Condition'] < 0.4) | 
                       (workers['Cum_Exp'] >= LIMIT_EXPOSURE) |
                       (~workers['is_present']))]
    
    for idx in to_exit.index:
        w = workers.loc[idx]
        st.session_state.workers.at[idx, 'Status'] = '퇴근'
        
        if w['Cum_Exp'] >= LIMIT_EXPOSURE:
            reason = "노출량 초과"
        elif w['Condition'] < 0.4:
            reason = "긴급보건"
        else:
            reason = "교대시간"
        st.session_state.log.append(f"🚨 {w['ID']} 교체 ({reason})")

    # 무한 루프 리셋 (대기자 부족 시)
    if len(workers[(workers['Status'] == '대기') & (workers['is_present'])]) < 5:
        reset_mask = (st.session_state.workers['Status'] == '퇴근') & (st.session_state.workers['is_present'])
        st.session_state.workers.loc[reset_mask, 'Work_Time'] = 0.0
        st.session_state.workers.loc[reset_mask, 'Status'] = '대기'
        st.session_state.workers.loc[reset_mask, 'Condition'] = 1.0
        st.session_state.workers.loc[reset_mask, 'Cum_Exp'] = 0.0
        st.session_state.log.append("♻️ 전원 휴식 및 데이터 리셋")

    # 투입 (12명 유지) - 💡 도장 라인 12칸을 꽉 채우기 위해 12명으로 수정
    current_duty = st.session_state.workers[st.session_state.workers['Status'] == '근무']
    if len(current_duty) < 12:
        needed = 12 - len(current_duty)
        available = st.session_state.workers[(st.session_state.workers['Status'] == '대기') & (st.session_state.workers['is_present'])].sort_values('Cum_Exp')
        for idx in available.iloc[:needed].index:
            st.session_state.workers.at[idx, 'Status'] = '근무'

    # B. 배정 및 시각화 (12명)
    on_duty = st.session_state.workers[st.session_state.workers['Status'] == '근무'].head(12)
    
    if len(on_duty) == 12:
        voc_matrix = np.random.randint(10, 100, (2, 6))
        booths = [{'X': c+1, 'Y': r+1, 'VOC': voc_matrix[r, c]} for r in range(2) for c in range(6)]
        
        # 💡 12명을 12자리에 배정
        cost_matrix = np.zeros((12, 12))
        for i in range(12):
            w = on_duty.iloc[i]
            for j in range(12):
                b = booths[j]
                sens = 2.0 if w['Level'] == '신입' else 1.0
                cost_matrix[i, j] = (sens * b['VOC'] + w['Cum_Exp']) / (w['Skill_Weight'] * w['Condition'])
        
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        col_left, col_right = st.columns([2.2, 1.2])
        
        with col_left:
            st.subheader("🌐 실시간 공정 히트맵 (도장 라인)")
            fig = go.Figure(go.Heatmap(z=voc_matrix, x=[1,2,3,4,5,6], y=[1,2], colorscale='RdYlGn_r', zmin=0, zmax=100, opacity=0.4))
            
            fig.add_annotation(x=1.5, y=2.8, text="<b>Primer</b>", showarrow=False, font=dict(size=15, color="#555"))
            fig.add_annotation(x=3.5, y=2.8, text="<b>Basecoat</b>", showarrow=False, font=dict(size=15, color="#555"))
            fig.add_annotation(x=5.5, y=2.8, text="<b>Clearcoat</b>", showarrow=False, font=dict(size=15, color="#555"))
            
            fig.add_vline(x=2.5, line_dash="dash", line_color="rgba(100, 100, 100, 0.5)", line_width=2)
            fig.add_vline(x=4.5, line_dash="dash", line_color="rgba(100, 100, 100, 0.5)", line_width=2)
            
            for i in range(len(row_ind)):
                w = on_duty.iloc[row_ind[i]]
                b = booths[col_ind[i]]
                
                st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Work_Time'] += 0.5
                st.session_state.workers.loc[st.session_state.workers['ID'] == w['ID'], 'Cum_Exp'] += b['VOC'] * 0.1 
                
                border = 'red' if w['Condition'] < 0.5 else ('orange' if w['Cum_Exp'] > 80 else 'white')
                fig.add_trace(go.Scatter(x=[b['X']], y=[b['Y']], mode="markers+text",
                    marker=dict(size=45, color=st.session_state.colors[w['ID']], line=dict(width=4, color=border)),
                    text=[f"<b>{w['ID']}</b>"], textposition="middle center", showlegend=False))
                
            fig.update_layout(
                yaxis=dict(range=[0.5, 3.2]), 
                height=450, 
                margin=dict(l=10, r=10, t=10, b=10)
            )
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        with col_right:
            st.subheader("📊 안전 데이터 보드")
            
            # 임계치 및 현재 값 불러오기 (TDI 제거)
            THRESHOLDS = {'Toluene': 50, 'Xylene': 100, 'Ketone': 200, 'HDI': 0.005}
            t_tol = float(workers['TWA_toluene'].iloc[0])
            t_xyl = float(workers['TWA_Xylene'].iloc[0])
            t_ket = float(workers['TWA_Ketone'].iloc[0])
            t_hdi = float(workers['TWA_HDI'].iloc[0])
            
            # 하나라도 초과했는지 통합 검사
            is_alert = any([
                t_tol > THRESHOLDS['Toluene'], t_xyl > THRESHOLDS['Xylene'], 
                t_ket > THRESHOLDS['Ketone'], t_hdi > THRESHOLDS['HDI']
            ])

            # 💡 [수정] Isocyanate 단일 렌더링
            st.markdown("### ☠️ Isocyanate")
            st.caption("입자상+가스상 혼재로 감지가 어려우며 극미량으로도 치명적입니다.")
            st.markdown(metric_card("HDI 시간가중평균(TWA)", t_hdi, THRESHOLDS['HDI'], decimal=3), unsafe_allow_html=True)

            # 기존 용제 구역
            st.markdown("### 🧪 일반 용제 TWA 현황")
            twa_cols = st.columns(3)
            with twa_cols[0]:
                st.markdown(metric_card("Toluene", t_tol, THRESHOLDS['Toluene']), unsafe_allow_html=True)
            with twa_cols[1]:
                st.markdown(metric_card("Xylene", t_xyl, THRESHOLDS['Xylene']), unsafe_allow_html=True)
            with twa_cols[2]:
                st.markdown(metric_card("Ketone", t_ket, THRESHOLDS['Ketone']), unsafe_allow_html=True)
            
            # 전체 알림 메시지
            if is_alert:
                st.error("🚨 경고: 붉은색으로 표시된 유해물질이 노출 기준치를 초과했습니다! 즉각적인 환기 및 보호구 점검이 필요합니다.")
            else:
                st.success("✅ 모든 유해물질 수치가 안전 기준치 이내로 유지되고 있습니다.")
            
            st.divider()
            
            # 상태 테이블 (12명 표시)
            status_df = on_duty[['ID', 'Level', 'Condition', 'Work_Time', 'Cum_Exp']].copy()
            status_df.columns = ['ID', '숙련도', '컨디션', '시간(s)', '누적 노출량']
            
            st.dataframe(
                status_df.sort_values('누적 노출량', ascending=False).style.format({
                    '컨디션': '{:.2f}', '시간(s)': '{:.1f}', '누적 노출량': '{:.1f}'
                }).background_gradient(subset=['누적 노출량'], cmap='YlOrRd'),
                hide_index=True, use_container_width=True
            )
            st.caption("최근 안전 로그")
            for l in st.session_state.log[-3:]: 
                st.write(f"· {l}")
    else:
        st.error("🚨 인력 부족! 공정 가동이 일시 중단되었습니다. (최소 12명 필요)")

st.title("🛡️ YULfactory: 산업안전보건 지능형 관제 시스템")
update_dashboard()