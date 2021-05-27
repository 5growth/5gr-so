### Project information
5GROWTH is funded by the European Union’s Research and Innovation Programme Horizon 2020 under Grant Agreement no. 856709


Call: H2020-ICT-2019. Topic: ICT-19-2019. Type of action: RIA. Duration: 30 Months. Start date: 1/6/2019


<p align="center">
<img src="https://upload.wikimedia.org/wikipedia/commons/b/b7/Flag_of_Europe.svg" width="100px" />
</p>

<p align="center">
<img src="https://5g-ppp.eu/wp-content/uploads/2019/06/5Growth_rgb_horizontal.png" width="300px" />
</p>
 



# 5Growth-SO

Release Two of 5Growth-SO validates the final integration of different innovations developed during 5Growth project.
This Release has been built upon Release 1 of 5Growth-SO, enhancing the Final Release of 5GT-SO (available at: https://github.com/5g-transformer ).
Further information and explanations can be found in deliverables D2.3 "Final Design and Evaluation of the innovations of the 5G End-to-End Service Platform " 
and D2.4 "Final implementation of 5G End-to-End Service Platform" (available at http://5growth.eu/deliverables/ ).
Documentation and installation instructions are included in /5Gr-SO/documentation folder.

## Final Release Features:

### Extended REST-based NBI (I1: RAN segment in network slices and I6: E2E Orchestration: Federation and Inter-Domain )
- Modification of NBI to accept slice-based parameters to manage RAN network slices
- Modification of NBI to perform PNFD management for supporting RAN network slices
- NBI extension supporting the interaction (i.e. lifecycle management) with 5G-EVE platform (https://www.5g-eve.eu/) for multi-domain scenarios 

### Integration with 5Growth Vertical-Service monitoring system (I2: Vertical-service monitoring and I3: Monitoring Orchestration)
- Extension of the Cloudify wrapper, the OSM wrapper and the Monitoring manager submodules to request the creation and configuration of Remote Virtual Maching (RVM)
  agents and the execution of Day-1 scripts embedded in the network service descriptor in conjunction with the 5Gr-Vertical-Service monitoring system and the 5Gr-Resource layer
- Prometheus collectors creation/deletion through the RVM agents (node exporter, blackbox exporter)
- Development and integration of a custom prometheus exporter for collecting customer metrics (PECCM)
- Support of native and 3rd-party client-side monitoring probes (e.g., latency probe)
- Support for VNF log monitoring probes

### Addition of close control-loops for scaling operations (I4: Control-loops stability & I5: AI/ML support)
- Extension of SLA Manager to process new AI/ML information element defined in NSD, and to orchestrate the 5Gr-VoMS platform and the new added streaming platform (Apache Spark) to manage continuous close-loop AI/ML scaling based 
  operations 
- Extension of SLA Manager to interact with 5Gr-AI/ML platform to perform AI/ML model retrieval and metric collection to enhance available datasets.
- Addition of AI/ML repository to store downloaded AI/ML models for AI/ML scale-based operations

### Scaling of composite and federated NFV-NS deployments (I6: E2E Orchestration: Federation and Inter-Domain)
- Evolution of service orchestration and resource orchestration modules to support scaling operations of composite NFV-NS including multi-domain scenarios. The
  scaling operations can be directed to the composite deployment or the different constituent nested NFV-NS

### Support of enhanced resource orchestration algorithms (I8: Smart Orchestration and Resource Control)
- Enhancement of Resource Orchestration module to handle different abstraction mechanisms (e.g., Connectivity Service Abstraction (CSA) vs Infrastructure Abstraction (InA)) in conjunction with
5Gr-Resource Layer


### Support for lifecycle management actions based on forecasted monitoring metrics  (I10: Forecasting and Inference)
- Definition of Forecasting Information Elements at the NSD and processing at Monitoring Manager and SLA Manager modules to interact with the Forecasting Functional Block (FFB) and launch
forecasting jobs in conjuntion with AI/ML-based scaling operation

### Support for the 5Growth CI/CD containerized environment (I12: 5Growth CI/CD)
- Addition of the Jenkinsfile allowing CI/CD deployments 

### Enhanced GUI & complementary features
- Representation and visualization of PNF descriptors
- Notification system reporting lifecycle management operations (instantiation, scaling, termination)
- Improved logging tracing feeding data-engineering pipelines for automatic orchestration operation processing
