FROM apache/airflow:3.3.1

ARG AIRFLOW_VERSION=3.3.1

COPY --chown=airflow:root data_platform/airflow/requirements.txt /opt/airflow/requirements.txt

RUN pip install --no-cache-dir \
      "apache-airflow==${AIRFLOW_VERSION}" \
      -r /opt/airflow/requirements.txt \
    && pip check
