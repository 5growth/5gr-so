# 5Growth-SO

Release One of 5Growth-SO bases on the Final Release of 5GT-SO (available at: https://github.com/5g-transformer ) and 
supports the first set of additional innovations provided during the first year of 5Growth. Further information can be found in deliverable
"D2.2: Initial implementation of 5G End-to-End Service Platform" (available at http://5growth.eu/deliverables/ )

## Release 1 Features

### Extended REST-based NBI (I1: RAN segment in network slices)
- Modification of NBI to accept slice-based parameters to manage RAN network slices. Further support will be provided in R2.

### Integration with 5Growth Vertical-Service monitoring system (I2: Vertical-service monitoring)
- Extension of the Cloudify wrapper and the Monitoring manager submodules to request the creation and configuration of RVM agents
  in conjunction with the 5Gr-Monitoring platform and the 5Gr-Resource layer.

### Addition of close control-loops for scaling operations (I4: Control-loops stability)
- Extension of SLA Manager to orchestrate the 5Gr-Monitoring platform and the new added streaming platform (Apache Spark) to perform AI/ML scaling based 
  operations. Further support in terms of interaction with the 5Gr-AIML platform will be provided in R2.

### Support for the 5Growth CI/CD containerized environment (I12)
- Addition of the Jenkinsfile allowing CI/CD deployments 
